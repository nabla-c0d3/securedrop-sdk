import datetime
import http
import json
import os
import shutil
import tempfile
import time
import unittest
from subprocess import TimeoutExpired

import pyotp
import pytest

from sdclientapi import API, RequestTimeoutError
from sdclientapi.sdlocalobjects import (
    BaseError,
    Reply,
    ReplyError,
    Source,
    Submission,
    WrongUUIDError,
)
from utils import dastollervey_datasaver, load_auth, save_auth

NUM_REPLIES_PER_SOURCE = 2


class TestAPIProxy(unittest.TestCase):
    @dastollervey_datasaver
    def setUp(self):
        self.totp = pyotp.TOTP("JHCOGO7VCER3EJ4L")
        self.username = "journalist"
        self.password = "correct horse battery staple profanity oil chewy"
        self.server = "http://localhost:8081/"
        self.api = API(self.server, self.username, self.password, str(self.totp.now()), proxy=True)

        for i in range(3):
            if os.path.exists("testtoken.json"):
                token = load_auth()
                self.api.token = token
                self.api.update_auth_header()
                break

            # The following is True when we did a logout
            if os.path.exists("logout.txt"):
                os.unlink("logout.txt")
                time.sleep(31)
            # Now let us try to login
            try:
                self.api = API(
                    self.server, self.username, self.password, str(self.totp.now()), proxy=True
                )
                self.api.authenticate()
                with open("login.txt", "w") as fobj:
                    fobj.write("in")
            except Exception as err:
                print(err)
                time.sleep(31)
                continue

            save_auth(self.api.token)
            break

    def test_api_auth(self):

        self.assertTrue(isinstance(self.api.token, str))
        self.assertTrue(isinstance(self.api.token_expiration, datetime.datetime))
        self.assertTrue(isinstance(self.api.token_journalist_uuid, str))
        self.assertTrue(isinstance(self.api.first_name, (str, type(None))))
        self.assertTrue(isinstance(self.api.last_name, (str, type(None))))

    @dastollervey_datasaver
    def test_seen(self):
        submissions = self.api.get_all_submissions()
        replies = self.api.get_all_replies()

        file_uuids = []
        message_uuids = []
        reply_uuids = []

        for submission in submissions:
            if submission.is_file():
                file_uuids.append(submission.uuid)
            else:
                message_uuids.append(submission.uuid)

        for reply in replies:
            reply_uuids.append(reply.uuid)

        self.assertTrue(
            self.api.seen(files=file_uuids, messages=message_uuids, replies=reply_uuids)
        )

    @dastollervey_datasaver
    def test_get_sources(self):
        sources = self.api.get_sources()
        for source in sources:
            # Assert expected fields are present
            assert source.journalist_designation
            assert source.uuid
            assert source.last_updated

    @dastollervey_datasaver
    def test_star_add_remove(self):
        s = self.api.get_sources()[0]
        self.assertTrue(self.api.add_star(s))
        self.assertTrue(self.api.remove_star(s))
        for source in self.api.get_sources():
            if source.uuid == s.uuid:
                self.assertFalse(source.is_starred)

    @dastollervey_datasaver
    def test_get_single_source(self):
        s = self.api.get_sources()[0]
        # Now we will try to get the same source again
        s2 = self.api.get_source(s)

        self.assertEqual(s.journalist_designation, s2.journalist_designation)
        self.assertEqual(s.uuid, s2.uuid)

    @dastollervey_datasaver
    def test_get_single_source_from_string(self):
        s = self.api.get_sources()[0]
        # Now we will try to get the same source again using uuid
        s2 = self.api.get_source_from_string(s.uuid)

        self.assertEqual(s.journalist_designation, s2.journalist_designation)
        self.assertEqual(s.uuid, s2.uuid)

    @dastollervey_datasaver
    def test_failed_single_source(self):
        with self.assertRaises(WrongUUIDError):
            self.api.get_source(Source(uuid="not there"))

    @dastollervey_datasaver
    def test_get_submissions(self):
        s = self.api.get_sources()[0]

        subs = self.api.get_submissions(s)
        for submission in subs:
            assert submission.filename

    @dastollervey_datasaver
    def test_get_submission(self):
        # Get a source with submissions
        source_uuid = self.api.get_all_submissions()[0].source_uuid
        s = self.api.get_source(Source(uuid=source_uuid))

        subs = self.api.get_submissions(s)
        sub = self.api.get_submission(subs[0])
        self.assertEqual(sub.filename, subs[0].filename)

    @dastollervey_datasaver
    def test_get_submission_from_string(self):
        # Get a source with submissions
        source_uuid = self.api.get_all_submissions()[0].source_uuid
        s = self.api.get_source(Source(uuid=source_uuid))

        subs = self.api.get_submissions(s)
        sub = self.api.get_submission_from_string(subs[0].uuid, s.uuid)
        self.assertEqual(sub.filename, subs[0].filename)

    @dastollervey_datasaver
    def test_get_wrong_submissions(self):
        s = self.api.get_sources()[0]
        s.uuid = "rofl-missing"
        with self.assertRaises(WrongUUIDError):
            self.api.get_submissions(s)

    @dastollervey_datasaver
    def test_get_all_submissions(self):
        subs = self.api.get_all_submissions()
        for submission in subs:
            assert submission.filename

    @dastollervey_datasaver
    def test_flag_source(self):
        s = self.api.get_sources()[0]
        self.assertTrue(self.api.flag_source(s))
        # Now we will try to get the same source again
        s2 = self.api.get_source(s)
        self.assertTrue(s2.is_flagged)

    @dastollervey_datasaver
    def test_delete_source(self):
        number_of_sources_before = len(self.api.get_sources())

        s = self.api.get_sources()[0]
        self.assertTrue(self.api.delete_source(s))

        # Now there should be one less source
        sources = self.api.get_sources()
        self.assertEqual(len(sources), number_of_sources_before - 1)

    @dastollervey_datasaver
    def test_delete_source_from_string(self):
        number_of_sources_before = len(self.api.get_sources())

        s = self.api.get_sources()[0]
        self.assertTrue(self.api.delete_source_from_string(s.uuid))

        # Now there should be one less source
        sources = self.api.get_sources()
        self.assertEqual(len(sources), number_of_sources_before - 1)

    @dastollervey_datasaver
    def test_delete_submission(self):
        number_of_submissions_before = len(self.api.get_all_submissions())

        subs = self.api.get_all_submissions()
        self.assertTrue(self.api.delete_submission(subs[0]))
        new_subs = self.api.get_all_submissions()
        # We now should have 1 less submission
        self.assertEqual(len(new_subs), number_of_submissions_before - 1)

        # Let us make sure that sub[0] is not there
        for s in new_subs:
            self.assertNotEqual(s.uuid, subs[0].uuid)

    @dastollervey_datasaver
    def test_delete_submission_from_string(self):
        number_of_submissions_before = len(self.api.get_all_submissions())

        s = self.api.get_sources()[0]

        subs = self.api.get_submissions(s)

        self.assertTrue(self.api.delete_submission(subs[0]))
        new_subs = self.api.get_all_submissions()
        # We now should have 1 less submission
        self.assertEqual(len(new_subs), number_of_submissions_before - 1)

        # Let us make sure that sub[0] is not there
        for s in new_subs:
            self.assertNotEqual(s.uuid, subs[0].uuid)

    @dastollervey_datasaver
    def test_get_current_user(self):
        user = self.api.get_current_user()
        self.assertTrue(user["is_admin"])
        self.assertEqual(user["username"], "journalist")
        self.assertTrue("first_name" in user)
        self.assertTrue("last_name" in user)

    @dastollervey_datasaver
    def test_get_users(self):
        users = self.api.get_users()
        for user in users:
            # Assert expected fields are present
            assert hasattr(user, "first_name")
            assert hasattr(user, "last_name")
            # Every user has a non-empty name and UUID
            assert user.username
            assert user.uuid
            # The API should never return these fields
            assert not hasattr(user, "last_login")
            assert not hasattr(user, "is_admin")

    @dastollervey_datasaver
    def test_error_unencrypted_reply(self):
        s = self.api.get_sources()[0]
        with self.assertRaises(ReplyError) as err:
            self.api.reply_source(s, "hello")

        self.assertEqual(err.exception.msg, "bad request")

    @dastollervey_datasaver
    def test_reply_source(self):
        s = self.api.get_sources()[0]
        dirname = os.path.dirname(__file__)
        with open(os.path.join(dirname, "encrypted_msg.asc")) as fobj:
            data = fobj.read()

        reply = self.api.reply_source(s, data)
        assert isinstance(reply, Reply)
        assert reply.uuid
        assert reply.filename

    @dastollervey_datasaver
    def test_reply_source_with_uuid(self):
        s = self.api.get_sources()[0]
        dirname = os.path.dirname(__file__)
        with open(os.path.join(dirname, "encrypted_msg.asc")) as fobj:
            data = fobj.read()

        msg_uuid = "e467868c-1fbb-4b5e-bca2-87944ea83855"
        reply = self.api.reply_source(s, data, msg_uuid)
        assert reply.uuid == msg_uuid

    @dastollervey_datasaver
    def test_download_submission(self):
        s = self.api.get_all_submissions()[0]

        self.assertFalse(s.is_read)

        # We need a temporary directory to download
        tmpdir = tempfile.mkdtemp()
        _, filepath = self.api.download_submission(s, tmpdir)

        # Uncomment the following part only on QubesOS
        # for testing against real server.
        # now let us read the downloaded file
        # with open(filepath, "rb") as fobj:
        #    fobj.read()

        # is_read should still be False as of SecureDrop 1.6.0 or later.

        s = self.api.get_submission(s)
        self.assertFalse(s.is_read)

        # Let us remove the temporary directory
        shutil.rmtree(tmpdir)

    @dastollervey_datasaver
    def test_get_replies_from_source(self):
        s = self.api.get_sources()[0]
        replies = self.api.get_replies_from_source(s)
        self.assertEqual(len(replies), NUM_REPLIES_PER_SOURCE)

    @dastollervey_datasaver
    def test_get_reply_from_source(self):
        s = self.api.get_sources()[0]
        replies = self.api.get_replies_from_source(s)
        reply = replies[0]

        r = self.api.get_reply_from_source(s, reply.uuid)

        self.assertEqual(reply.filename, r.filename)
        self.assertEqual(reply.size, r.size)
        self.assertEqual(reply.reply_url, r.reply_url)
        self.assertEqual(reply.journalist_username, r.journalist_username)

    @dastollervey_datasaver
    def test_get_all_replies(self):
        num_sources = len(self.api.get_sources())
        replies = self.api.get_all_replies()
        self.assertEqual(len(replies), NUM_REPLIES_PER_SOURCE * num_sources)

    @dastollervey_datasaver
    def test_download_reply(self):
        r = self.api.get_all_replies()[0]

        # We need a temporary directory to download
        tmpdir = tempfile.mkdtemp()
        _, filepath = self.api.download_reply(r, tmpdir)

        # Uncomment the following part only on QubesOS
        # for testing against real server.
        # now let us read the downloaded file
        # with open(filepath, "rb") as fobj:
        #     fobj.read()

        # Let us remove the temporary directory
        shutil.rmtree(tmpdir)

    @dastollervey_datasaver
    def test_delete_reply(self):
        r = self.api.get_all_replies()[0]

        number_of_replies_before = len(self.api.get_all_replies())

        self.assertTrue(self.api.delete_reply(r))

        # We deleted one, so there must be 1 less reply now
        self.assertEqual(len(self.api.get_all_replies()), number_of_replies_before - 1)

    @dastollervey_datasaver
    def test_logout(self):
        r = self.api.logout()
        self.assertTrue(r)
        if os.path.exists("login.txt"):
            os.unlink("login.txt")
        if os.path.exists("testtoken.json"):
            os.unlink("testtoken.json")
        with open("logout.txt", "w") as fobj:
            fobj.write("out")


def test_request_timeout(mocker):
    class MockedPopen:
        def __init__(self, *nargs, **kwargs) -> None:
            self.stdin = mocker.MagicMock()

        def communicate(self, *nargs, **kwargs) -> None:
            raise TimeoutExpired(["mock"], 123)

    api = API("mock", "mock", "mock", "mock", proxy=True)
    mocker.patch("sdclientapi.Popen", MockedPopen)

    with pytest.raises(RequestTimeoutError):
        api.authenticate()


def test_download_reply_timeout(mocker):
    class MockedPopen:
        def __init__(self, *nargs, **kwargs) -> None:
            self.stdin = mocker.MagicMock()

        def communicate(self, *nargs, **kwargs) -> None:
            raise TimeoutExpired(["mock"], 123)

    api = API("mock", "mock", "mock", "mock", proxy=True)
    mocker.patch("sdclientapi.Popen", MockedPopen)
    with pytest.raises(RequestTimeoutError):
        r = Reply(uuid="humanproblem", filename="secret.txt")
        api.download_reply(r)


def test_download_submission_timeout(mocker):
    class MockedPopen:
        def __init__(self, *nargs, **kwargs) -> None:
            self.stdin = mocker.MagicMock()

        def communicate(self, *nargs, **kwargs) -> None:
            raise TimeoutExpired(["mock"], 123)

    api = API("mock", "mock", "mock", "mock", proxy=True)
    mocker.patch("sdclientapi.Popen", MockedPopen)
    with pytest.raises(RequestTimeoutError):
        s = Submission(uuid="climateproblem")
        api.download_submission(s)


def test_download_get_sources_error_request_timeout(mocker):
    api = API("mock", "mock", "mock", "mock", True)
    mocker.patch(
        "sdclientapi.json_query",
        return_value=(
            json.dumps(
                {
                    "body": json.dumps({"error": "wah"}),
                    "status": http.HTTPStatus.GATEWAY_TIMEOUT,
                    "headers": "foo",
                }
            )
        ),
    )
    with pytest.raises(RequestTimeoutError):
        api.get_sources()


def test_filename_key_not_in_download_response(mocker):
    api = API("mock", "mock", "mock", "mock", True)
    s = Submission(uuid="foobar")
    mocker.patch(
        "sdclientapi.json_query",
        return_value=(
            json.dumps({"body": json.dumps({"error": "wah"}), "status": 200, "headers": "foo"})
        ),
    )
    with pytest.raises(BaseError):
        api.download_submission(s)
