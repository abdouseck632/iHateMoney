from collections import defaultdict
import io
import json
import re
from time import sleep
import unittest
from unittest.mock import MagicMock

from flask import session
from werkzeug.security import check_password_hash, generate_password_hash

from ihatemoney import models
from ihatemoney.tests.common.ihatemoney_testcase import IhatemoneyTestCase
from ihatemoney.versioning import LoggingMode


class BudgetTestCase(IhatemoneyTestCase):
    def test_notifications(self):
        """Test that the notifications are sent, and that email addresses
        are checked properly.
        """
        # sending a message to one person
        with self.app.mail.record_messages() as outbox:

            # create a project
            self.login("raclette")

            self.post_project("raclette")
            resp = self.client.post(
                "/raclette/invite",
                data={"emails": "zorglub@notmyidea.org"},
                follow_redirects=True,
            )

            # success notification
            self.assertIn("Your invitations have been sent", resp.data.decode("utf-8"))

            self.assertEqual(len(outbox), 2)
            self.assertEqual(outbox[0].recipients, ["raclette@notmyidea.org"])
            self.assertEqual(outbox[1].recipients, ["zorglub@notmyidea.org"])

        # sending a message to multiple persons
        with self.app.mail.record_messages() as outbox:
            self.client.post(
                "/raclette/invite",
                data={"emails": "zorglub@notmyidea.org, toto@notmyidea.org"},
            )

            # only one message is sent to multiple persons
            self.assertEqual(len(outbox), 1)
            self.assertEqual(
                outbox[0].recipients, ["zorglub@notmyidea.org", "toto@notmyidea.org"]
            )

        # mail address checking
        with self.app.mail.record_messages() as outbox:
            response = self.client.post("/raclette/invite", data={"emails": "toto"})
            self.assertEqual(len(outbox), 0)  # no message sent
            self.assertIn("The email toto is not valid", response.data.decode("utf-8"))

        # mixing good and wrong addresses shouldn't send any messages
        with self.app.mail.record_messages() as outbox:
            self.client.post(
                "/raclette/invite", data={"emails": "zorglub@notmyidea.org, zorglub"}
            )  # not valid

            # only one message is sent to multiple persons
            self.assertEqual(len(outbox), 0)

    def test_invite(self):
        """Test that invitation e-mails are sent properly"""
        self.login("raclette")
        self.post_project("raclette")
        with self.app.mail.record_messages() as outbox:
            self.client.post("/raclette/invite", data={"emails": "toto@notmyidea.org"})
            self.assertEqual(len(outbox), 1)
            url_start = outbox[0].body.find("You can log in using this link: ") + 32
            url_end = outbox[0].body.find(".\n", url_start)
            url = outbox[0].body[url_start:url_end]
        self.client.get("/exit")
        # Test that we got a valid token
        resp = self.client.get(url, follow_redirects=True)
        self.assertIn(
            'You probably want to <a href="/raclette/members/add"',
            resp.data.decode("utf-8"),
        )
        # Test empty and invalid tokens
        self.client.get("/exit")
        resp = self.client.get("/authenticate")
        self.assertIn("You either provided a bad token", resp.data.decode("utf-8"))
        resp = self.client.get("/authenticate?token=token")
        self.assertIn("You either provided a bad token", resp.data.decode("utf-8"))

    def test_password_reminder(self):
        # test that it is possible to have an email containing the password of a
        # project in case people forget it (and it happens!)

        self.create_project("raclette")

        with self.app.mail.record_messages() as outbox:
            # a nonexisting project should not send an email
            self.client.post("/password-reminder", data={"id": "unexisting"})
            self.assertEqual(len(outbox), 0)

            # a mail should be sent when a project exists
            self.client.post("/password-reminder", data={"id": "raclette"})
            self.assertEqual(len(outbox), 1)
            self.assertIn("raclette", outbox[0].body)
            self.assertIn("raclette@notmyidea.org", outbox[0].recipients)

    def test_password_reset(self):
        # test that a password can be changed using a link sent by mail

        self.create_project("raclette")
        # Get password resetting link from mail
        with self.app.mail.record_messages() as outbox:
            resp = self.client.post(
                "/password-reminder", data={"id": "raclette"}, follow_redirects=True
            )
            # Check that we are redirected to the right page
            self.assertIn(
                "A link to reset your password has been sent to you",
                resp.data.decode("utf-8"),
            )
            # Check that an email was sent
            self.assertEqual(len(outbox), 1)
            url_start = outbox[0].body.find("You can reset it here: ") + 23
            url_end = outbox[0].body.find(".\n", url_start)
            url = outbox[0].body[url_start:url_end]
        # Test that we got a valid token
        resp = self.client.get(url)
        self.assertIn("Password confirmation</label>", resp.data.decode("utf-8"))
        # Test that password can be changed
        self.client.post(
            url, data={"password": "pass", "password_confirmation": "pass"}
        )
        resp = self.login("raclette", password="pass")
        self.assertIn(
            "<title>Account manager - raclette</title>", resp.data.decode("utf-8")
        )
        # Test empty and null tokens
        resp = self.client.get("/reset-password")
        self.assertIn("No token provided", resp.data.decode("utf-8"))
        resp = self.client.get("/reset-password?token=token")
        self.assertIn("Invalid token", resp.data.decode("utf-8"))

    def test_project_creation(self):
        with self.app.test_client() as c:

            with self.app.mail.record_messages() as outbox:
                # add a valid project
                resp = c.post(
                    "/create",
                    data={
                        "name": "The fabulous raclette party",
                        "id": "raclette",
                        "password": "party",
                        "contact_email": "raclette@notmyidea.org",
                        "default_currency": "USD",
                    },
                    follow_redirects=True,
                )
                # an email is sent to the owner with a reminder of the password
                self.assertEqual(len(outbox), 1)
                self.assertEqual(outbox[0].recipients, ["raclette@notmyidea.org"])
                self.assertIn(
                    "A reminder email has just been sent to you",
                    resp.data.decode("utf-8"),
                )

            # session is updated
            self.assertTrue(session["raclette"])

            # project is created
            self.assertEqual(len(models.Project.query.all()), 1)

            # Add a second project with the same id
            models.Project.query.get("raclette")

            c.post(
                "/create",
                data={
                    "name": "Another raclette party",
                    "id": "raclette",  # already used !
                    "password": "party",
                    "contact_email": "raclette@notmyidea.org",
                    "default_currency": "USD",
                },
            )

            # no new project added
            self.assertEqual(len(models.Project.query.all()), 1)

    def test_project_creation_without_public_permissions(self):
        self.app.config["ALLOW_PUBLIC_PROJECT_CREATION"] = False
        with self.app.test_client() as c:
            # add a valid project
            c.post(
                "/create",
                data={
                    "name": "The fabulous raclette party",
                    "id": "raclette",
                    "password": "party",
                    "contact_email": "raclette@notmyidea.org",
                    "default_currency": "USD",
                },
            )

            # session is not updated
            self.assertNotIn("raclette", session)

            # project is not created
            self.assertEqual(len(models.Project.query.all()), 0)

    def test_project_creation_with_public_permissions(self):
        self.app.config["ALLOW_PUBLIC_PROJECT_CREATION"] = True
        with self.app.test_client() as c:
            # add a valid project
            c.post(
                "/create",
                data={
                    "name": "The fabulous raclette party",
                    "id": "raclette",
                    "password": "party",
                    "contact_email": "raclette@notmyidea.org",
                    "default_currency": "USD",
                },
            )

            # session is updated
            self.assertTrue(session["raclette"])

            # project is created
            self.assertEqual(len(models.Project.query.all()), 1)

    def test_project_deletion(self):

        with self.app.test_client() as c:
            c.post(
                "/create",
                data={
                    "name": "raclette party",
                    "id": "raclette",
                    "password": "party",
                    "contact_email": "raclette@notmyidea.org",
                    "default_currency": "USD",
                },
            )

            # project added
            self.assertEqual(len(models.Project.query.all()), 1)

            c.get("/raclette/delete")

            # project removed
            self.assertEqual(len(models.Project.query.all()), 0)

    def test_bill_placeholder(self):
        self.post_project("raclette")
        self.login("raclette")

        result = self.client.get("/raclette/")

        # Empty bill list and no members, should now propose to add members first
        self.assertIn(
            'You probably want to <a href="/raclette/members/add"',
            result.data.decode("utf-8"),
        )

        result = self.client.post("/raclette/members/add", data={"name": "zorglub"})

        result = self.client.get("/raclette/")

        # Empty bill with member, list should now propose to add bills
        self.assertIn(
            'You probably want to <a href="/raclette/add"', result.data.decode("utf-8")
        )

    def test_membership(self):
        self.post_project("raclette")
        self.login("raclette")

        # adds a member to this project
        self.client.post("/raclette/members/add", data={"name": "zorglub"})
        self.assertEqual(len(models.Project.query.get("raclette").members), 1)

        # adds him twice
        result = self.client.post("/raclette/members/add", data={"name": "zorglub"})

        # should not accept him
        self.assertEqual(len(models.Project.query.get("raclette").members), 1)

        # add fred
        self.client.post("/raclette/members/add", data={"name": "fred"})
        self.assertEqual(len(models.Project.query.get("raclette").members), 2)

        # check fred is present in the bills page
        result = self.client.get("/raclette/")
        self.assertIn("fred", result.data.decode("utf-8"))

        # remove fred
        self.client.post(
            "/raclette/members/%s/delete"
            % models.Project.query.get("raclette").members[-1].id
        )

        # as fred is not bound to any bill, he is removed
        self.assertEqual(len(models.Project.query.get("raclette").members), 1)

        # add fred again
        self.client.post("/raclette/members/add", data={"name": "fred"})
        fred_id = models.Project.query.get("raclette").members[-1].id

        # bound him to a bill
        result = self.client.post(
            "/raclette/add",
            data={
                "date": "2011-08-10",
                "what": "fromage à raclette",
                "payer": fred_id,
                "payed_for": [fred_id],
                "amount": "25",
            },
        )

        # remove fred
        self.client.post(f"/raclette/members/{fred_id}/delete")

        # he is still in the database, but is deactivated
        self.assertEqual(len(models.Project.query.get("raclette").members), 2)
        self.assertEqual(len(models.Project.query.get("raclette").active_members), 1)

        # as fred is now deactivated, check that he is not listed when adding
        # a bill or displaying the balance
        result = self.client.get("/raclette/")
        self.assertNotIn(
            (f"/raclette/members/{fred_id}/delete"), result.data.decode("utf-8")
        )

        result = self.client.get("/raclette/add")
        self.assertNotIn("fred", result.data.decode("utf-8"))

        # adding him again should reactivate him
        self.client.post("/raclette/members/add", data={"name": "fred"})
        self.assertEqual(len(models.Project.query.get("raclette").active_members), 2)

        # adding an user with the same name as another user from a different
        # project should not cause any troubles
        self.post_project("randomid")
        self.login("randomid")
        self.client.post("/randomid/members/add", data={"name": "fred"})
        self.assertEqual(len(models.Project.query.get("randomid").active_members), 1)

    def test_person_model(self):
        self.post_project("raclette")
        self.login("raclette")

        # adds a member to this project
        self.client.post("/raclette/members/add", data={"name": "zorglub"})
        zorglub = models.Project.query.get("raclette").members[-1]

        # should not have any bills
        self.assertFalse(zorglub.has_bills())

        # bound him to a bill
        self.client.post(
            "/raclette/add",
            data={
                "date": "2011-08-10",
                "what": "fromage à raclette",
                "payer": zorglub.id,
                "payed_for": [zorglub.id],
                "amount": "25",
            },
        )

        # should have a bill now
        zorglub = models.Project.query.get("raclette").members[-1]
        self.assertTrue(zorglub.has_bills())

    def test_member_delete_method(self):
        self.post_project("raclette")
        self.login("raclette")

        # adds a member to this project
        self.client.post("/raclette/members/add", data={"name": "zorglub"})

        # try to remove the member using GET method
        response = self.client.get("/raclette/members/1/delete")
        self.assertEqual(response.status_code, 405)

        # delete user using POST method
        self.client.post("/raclette/members/1/delete")
        self.assertEqual(len(models.Project.query.get("raclette").active_members), 0)
        # try to delete an user already deleted
        self.client.post("/raclette/members/1/delete")

    def test_demo(self):
        # test that a demo project is created if none is defined
        self.assertEqual([], models.Project.query.all())
        self.client.get("/demo")
        demo = models.Project.query.get("demo")
        self.assertTrue(demo is not None)

        self.assertEqual(["Amina", "Georg", "Alice"], [m.name for m in demo.members])
        self.assertEqual(demo.get_bills().count(), 3)

    def test_deactivated_demo(self):
        self.app.config["ACTIVATE_DEMO_PROJECT"] = False

        # test redirection to the create project form when demo is deactivated
        resp = self.client.get("/demo")
        self.assertIn('<a href="/create?project_id=demo">', resp.data.decode("utf-8"))

    def test_authentication(self):
        # try to authenticate without credentials should redirect
        # to the authentication page
        resp = self.client.post("/authenticate")
        self.assertIn("Authentication", resp.data.decode("utf-8"))

        # raclette that the login / logout process works
        self.create_project("raclette")

        # try to see the project while not being authenticated should redirect
        # to the authentication page
        resp = self.client.get("/raclette", follow_redirects=True)
        self.assertIn("Authentication", resp.data.decode("utf-8"))

        # try to connect with wrong credentials should not work
        with self.app.test_client() as c:
            resp = c.post("/authenticate", data={"id": "raclette", "password": "nope"})

            self.assertIn("Authentication", resp.data.decode("utf-8"))
            self.assertNotIn("raclette", session)

        # try to connect with the right credentials should work
        with self.app.test_client() as c:
            resp = c.post(
                "/authenticate", data={"id": "raclette", "password": "raclette"}
            )

            self.assertNotIn("Authentication", resp.data.decode("utf-8"))
            self.assertIn("raclette", session)
            self.assertTrue(session["raclette"])

            # logout should wipe the session out
            c.get("/exit")
            self.assertNotIn("raclette", session)

        # test that with admin credentials, one can access every project
        self.app.config["ADMIN_PASSWORD"] = generate_password_hash("pass")
        with self.app.test_client() as c:
            resp = c.post("/admin?goto=%2Fraclette", data={"admin_password": "pass"})
            self.assertNotIn("Authentication", resp.data.decode("utf-8"))
            self.assertTrue(session["is_admin"])

    def test_admin_authentication(self):
        self.app.config["ADMIN_PASSWORD"] = generate_password_hash("pass")
        # Disable public project creation so we have an admin endpoint to test
        self.app.config["ALLOW_PUBLIC_PROJECT_CREATION"] = False

        # test the redirection to the authentication page when trying to access admin endpoints
        resp = self.client.get("/create")
        self.assertIn('<a href="/admin?goto=%2Fcreate">', resp.data.decode("utf-8"))

        # test right password
        resp = self.client.post(
            "/admin?goto=%2Fcreate", data={"admin_password": "pass"}
        )
        self.assertIn('<a href="/create">/create</a>', resp.data.decode("utf-8"))

        # test wrong password
        resp = self.client.post(
            "/admin?goto=%2Fcreate", data={"admin_password": "wrong"}
        )
        self.assertNotIn('<a href="/create">/create</a>', resp.data.decode("utf-8"))

        # test empty password
        resp = self.client.post("/admin?goto=%2Fcreate", data={"admin_password": ""})
        self.assertNotIn('<a href="/create">/create</a>', resp.data.decode("utf-8"))

    def test_login_throttler(self):
        self.app.config["ADMIN_PASSWORD"] = generate_password_hash("pass")

        # Activate admin login throttling by authenticating 4 times with a wrong passsword
        self.client.post("/admin?goto=%2Fcreate", data={"admin_password": "wrong"})
        self.client.post("/admin?goto=%2Fcreate", data={"admin_password": "wrong"})
        self.client.post("/admin?goto=%2Fcreate", data={"admin_password": "wrong"})
        resp = self.client.post(
            "/admin?goto=%2Fcreate", data={"admin_password": "wrong"}
        )

        self.assertIn(
            "Too many failed login attempts, please retry later.",
            resp.data.decode("utf-8"),
        )
        # Change throttling delay
        from ihatemoney.web import login_throttler

        login_throttler._delay = 0.005
        # Wait for delay to expire and retry logging in
        sleep(1)
        resp = self.client.post(
            "/admin?goto=%2Fcreate", data={"admin_password": "wrong"}
        )
        self.assertNotIn(
            "Too many failed login attempts, please retry later.",
            resp.data.decode("utf-8"),
        )

    def test_manage_bills(self):
        self.post_project("raclette")

        # add two persons
        self.client.post("/raclette/members/add", data={"name": "zorglub"})
        self.client.post("/raclette/members/add", data={"name": "fred"})

        members_ids = [m.id for m in models.Project.query.get("raclette").members]

        # create a bill
        self.client.post(
            "/raclette/add",
            data={
                "date": "2011-08-10",
                "what": "fromage à raclette",
                "payer": members_ids[0],
                "payed_for": members_ids,
                "amount": "25",
            },
        )
        models.Project.query.get("raclette")
        bill = models.Bill.query.one()
        self.assertEqual(bill.amount, 25)

        # edit the bill
        self.client.post(
            f"/raclette/edit/{bill.id}",
            data={
                "date": "2011-08-10",
                "what": "fromage à raclette",
                "payer": members_ids[0],
                "payed_for": members_ids,
                "amount": "10",
            },
        )

        bill = models.Bill.query.one()
        self.assertEqual(bill.amount, 10, "bill edition")

        # delete the bill
        self.client.get(f"/raclette/delete/{bill.id}")
        self.assertEqual(0, len(models.Bill.query.all()), "bill deletion")

        # test balance
        self.client.post(
            "/raclette/add",
            data={
                "date": "2011-08-10",
                "what": "fromage à raclette",
                "payer": members_ids[0],
                "payed_for": members_ids,
                "amount": "19",
            },
        )

        self.client.post(
            "/raclette/add",
            data={
                "date": "2011-08-10",
                "what": "fromage à raclette",
                "payer": members_ids[1],
                "payed_for": members_ids[0],
                "amount": "20",
            },
        )

        self.client.post(
            "/raclette/add",
            data={
                "date": "2011-08-10",
                "what": "fromage à raclette",
                "payer": members_ids[1],
                "payed_for": members_ids,
                "amount": "17",
            },
        )

        balance = models.Project.query.get("raclette").balance
        self.assertEqual(set(balance.values()), set([19.0, -19.0]))

        # Bill with negative amount
        self.client.post(
            "/raclette/add",
            data={
                "date": "2011-08-12",
                "what": "fromage à raclette",
                "payer": members_ids[0],
                "payed_for": members_ids,
                "amount": "-25",
            },
        )
        bill = models.Bill.query.filter(models.Bill.date == "2011-08-12")[0]
        self.assertEqual(bill.amount, -25)

        # add a bill with a comma
        self.client.post(
            "/raclette/add",
            data={
                "date": "2011-08-01",
                "what": "fromage à raclette",
                "payer": members_ids[0],
                "payed_for": members_ids,
                "amount": "25,02",
            },
        )
        bill = models.Bill.query.filter(models.Bill.date == "2011-08-01")[0]
        self.assertEqual(bill.amount, 25.02)

    def test_weighted_balance(self):
        self.post_project("raclette")

        # add two persons
        self.client.post("/raclette/members/add", data={"name": "zorglub"})
        self.client.post(
            "/raclette/members/add", data={"name": "freddy familly", "weight": 4}
        )

        members_ids = [m.id for m in models.Project.query.get("raclette").members]

        # test balance
        self.client.post(
            "/raclette/add",
            data={
                "date": "2011-08-10",
                "what": "fromage à raclette",
                "payer": members_ids[0],
                "payed_for": members_ids,
                "amount": "10",
            },
        )

        self.client.post(
            "/raclette/add",
            data={
                "date": "2011-08-10",
                "what": "pommes de terre",
                "payer": members_ids[1],
                "payed_for": members_ids,
                "amount": "10",
            },
        )

        balance = models.Project.query.get("raclette").balance
        self.assertEqual(set(balance.values()), set([6, -6]))

    def test_trimmed_members(self):
        self.post_project("raclette")

        # Add two times the same person (with a space at the end).
        self.client.post("/raclette/members/add", data={"name": "zorglub"})
        self.client.post("/raclette/members/add", data={"name": "zorglub "})
        members = models.Project.query.get("raclette").members

        self.assertEqual(len(members), 1)

    def test_weighted_members_list(self):
        self.post_project("raclette")

        # add two persons
        self.client.post("/raclette/members/add", data={"name": "zorglub"})
        self.client.post("/raclette/members/add", data={"name": "tata", "weight": 1})

        resp = self.client.get("/raclette/")
        self.assertIn("extra-info", resp.data.decode("utf-8"))

        self.client.post(
            "/raclette/members/add", data={"name": "freddy familly", "weight": 4}
        )

        resp = self.client.get("/raclette/")
        self.assertNotIn("extra-info", resp.data.decode("utf-8"))

    def test_negative_weight(self):
        self.post_project("raclette")

        # Add one user and edit it to have a negative share
        self.client.post("/raclette/members/add", data={"name": "zorglub"})
        resp = self.client.post(
            "/raclette/members/1/edit", data={"name": "zorglub", "weight": -1}
        )

        # An error should be generated, and its weight should still be 1.
        self.assertIn('<p class="alert alert-danger">', resp.data.decode("utf-8"))
        self.assertEqual(len(models.Project.query.get("raclette").members), 1)
        self.assertEqual(models.Project.query.get("raclette").members[0].weight, 1)

    def test_rounding(self):
        self.post_project("raclette")

        # add members
        self.client.post("/raclette/members/add", data={"name": "zorglub"})
        self.client.post("/raclette/members/add", data={"name": "fred"})
        self.client.post("/raclette/members/add", data={"name": "tata"})

        # create bills
        self.client.post(
            "/raclette/add",
            data={
                "date": "2011-08-10",
                "what": "fromage à raclette",
                "payer": 1,
                "payed_for": [1, 2, 3],
                "amount": "24.36",
            },
        )

        self.client.post(
            "/raclette/add",
            data={
                "date": "2011-08-10",
                "what": "red wine",
                "payer": 2,
                "payed_for": [1],
                "amount": "19.12",
            },
        )

        self.client.post(
            "/raclette/add",
            data={
                "date": "2011-08-10",
                "what": "delicatessen",
                "payer": 1,
                "payed_for": [1, 2],
                "amount": "22",
            },
        )

        balance = models.Project.query.get("raclette").balance
        result = {}
        result[models.Project.query.get("raclette").members[0].id] = 8.12
        result[models.Project.query.get("raclette").members[1].id] = 0.0
        result[models.Project.query.get("raclette").members[2].id] = -8.12
        # Since we're using floating point to store currency, we can have some
        # rounding issues that prevent test from working.
        # However, we should obtain the same values as the theoretical ones if we
        # round to 2 decimals, like in the UI.
        for key, value in balance.items():
            self.assertEqual(round(value, 2), result[key])

    def test_edit_project(self):
        # A project should be editable

        self.post_project("raclette")
        new_data = {
            "name": "Super raclette party!",
            "contact_email": "zorglub@notmyidea.org",
            "password": "didoudida",
            "logging_preference": LoggingMode.ENABLED.value,
            "default_currency": "USD",
        }

        resp = self.client.post("/raclette/edit", data=new_data, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        project = models.Project.query.get("raclette")

        self.assertEqual(project.name, new_data["name"])
        self.assertEqual(project.contact_email, new_data["contact_email"])
        self.assertEqual(project.default_currency, new_data["default_currency"])
        self.assertTrue(check_password_hash(project.password, new_data["password"]))

        # Editing a project with a wrong email address should fail
        new_data["contact_email"] = "wrong_email"

        resp = self.client.post("/raclette/edit", data=new_data, follow_redirects=True)
        self.assertIn("Invalid email address", resp.data.decode("utf-8"))

    def test_dashboard(self):
        # test that the dashboard is deactivated by default
        resp = self.client.post(
            "/admin?goto=%2Fdashboard",
            data={"admin_password": "adminpass"},
            follow_redirects=True,
        )
        self.assertIn('<div class="alert alert-danger">', resp.data.decode("utf-8"))

        # test access to the dashboard when it is activated
        self.app.config["ACTIVATE_ADMIN_DASHBOARD"] = True
        self.app.config["ADMIN_PASSWORD"] = generate_password_hash("adminpass")
        resp = self.client.post(
            "/admin?goto=%2Fdashboard",
            data={"admin_password": "adminpass"},
            follow_redirects=True,
        )
        self.assertIn(
            "<thead><tr><th>Project</th><th>Number of members",
            resp.data.decode("utf-8"),
        )

    def test_statistics_page(self):
        self.post_project("raclette")
        response = self.client.get("/raclette/statistics")
        self.assertEqual(response.status_code, 200)

    def test_statistics(self):
        self.post_project("raclette")

        # add members
        self.client.post("/raclette/members/add", data={"name": "zorglub", "weight": 2})
        self.client.post("/raclette/members/add", data={"name": "fred"})
        self.client.post("/raclette/members/add", data={"name": "tata"})
        # Add a member with a balance=0 :
        self.client.post("/raclette/members/add", data={"name": "pépé"})

        # create bills
        self.client.post(
            "/raclette/add",
            data={
                "date": "2011-08-10",
                "what": "fromage à raclette",
                "payer": 1,
                "payed_for": [1, 2, 3],
                "amount": "10.0",
            },
        )

        self.client.post(
            "/raclette/add",
            data={
                "date": "2011-08-10",
                "what": "red wine",
                "payer": 2,
                "payed_for": [1],
                "amount": "20",
            },
        )

        self.client.post(
            "/raclette/add",
            data={
                "date": "2011-08-10",
                "what": "delicatessen",
                "payer": 1,
                "payed_for": [1, 2],
                "amount": "10",
            },
        )

        response = self.client.get("/raclette/statistics")
        regex = r"<td class=\"d-md-none\">{}</td>\s+<td>{}</td>\s+<td>{}</td>"
        self.assertRegex(
            response.data.decode("utf-8"),
            regex.format("zorglub", r"\$20\.00", r"\$31\.67"),
        )
        self.assertRegex(
            response.data.decode("utf-8"),
            regex.format("fred", r"\$20\.00", r"\$5\.83"),
        )
        self.assertRegex(
            response.data.decode("utf-8"), regex.format("tata", r"\$0\.00", r"\$2\.50")
        )
        self.assertRegex(
            response.data.decode("utf-8"), regex.format("pépé", r"\$0\.00", r"\$0\.00")
        )

        # Check that the order of participants in the sidebar table is the
        # same as in the main table.
        order = ["fred", "pépé", "tata", "zorglub"]
        regex1 = r".*".join(
            r"<td class=\"balance-name\">{}</td>".format(name) for name in order
        )
        regex2 = r".*".join(
            r"<td class=\"d-md-none\">{}</td>".format(name) for name in order
        )
        # Build the regexp ourselves to be able to pass the DOTALL flag
        # (so that ".*" matches newlines)
        self.assertRegex(response.data.decode("utf-8"), re.compile(regex1, re.DOTALL))
        self.assertRegex(response.data.decode("utf-8"), re.compile(regex2, re.DOTALL))

    def test_settle_page(self):
        self.post_project("raclette")
        response = self.client.get("/raclette/settle_bills")
        self.assertEqual(response.status_code, 200)

    def test_settle(self):
        self.post_project("raclette")

        # add members
        self.client.post("/raclette/members/add", data={"name": "zorglub"})
        self.client.post("/raclette/members/add", data={"name": "fred"})
        self.client.post("/raclette/members/add", data={"name": "tata"})
        # Add a member with a balance=0 :
        self.client.post("/raclette/members/add", data={"name": "pépé"})

        # create bills
        self.client.post(
            "/raclette/add",
            data={
                "date": "2011-08-10",
                "what": "fromage à raclette",
                "payer": 1,
                "payed_for": [1, 2, 3],
                "amount": "10.0",
            },
        )

        self.client.post(
            "/raclette/add",
            data={
                "date": "2011-08-10",
                "what": "red wine",
                "payer": 2,
                "payed_for": [1],
                "amount": "20",
            },
        )

        self.client.post(
            "/raclette/add",
            data={
                "date": "2011-08-10",
                "what": "delicatessen",
                "payer": 1,
                "payed_for": [1, 2],
                "amount": "10",
            },
        )
        project = models.Project.query.get("raclette")
        transactions = project.get_transactions_to_settle_bill()
        members = defaultdict(int)
        # We should have the same values between transactions and project balances
        for t in transactions:
            members[t["ower"]] -= t["amount"]
            members[t["receiver"]] += t["amount"]
        balance = models.Project.query.get("raclette").balance
        for m, a in members.items():
            assert abs(a - balance[m.id]) < 0.01
        return

    def test_settle_zero(self):
        self.post_project("raclette")

        # add members
        self.client.post("/raclette/members/add", data={"name": "zorglub"})
        self.client.post("/raclette/members/add", data={"name": "fred"})
        self.client.post("/raclette/members/add", data={"name": "tata"})

        # create bills
        self.client.post(
            "/raclette/add",
            data={
                "date": "2016-12-31",
                "what": "fromage à raclette",
                "payer": 1,
                "payed_for": [1, 2, 3],
                "amount": "10.0",
            },
        )

        self.client.post(
            "/raclette/add",
            data={
                "date": "2016-12-31",
                "what": "red wine",
                "payer": 2,
                "payed_for": [1, 3],
                "amount": "20",
            },
        )

        self.client.post(
            "/raclette/add",
            data={
                "date": "2017-01-01",
                "what": "refund",
                "payer": 3,
                "payed_for": [2],
                "amount": "13.33",
            },
        )
        project = models.Project.query.get("raclette")
        transactions = project.get_transactions_to_settle_bill()

        # There should not be any zero-amount transfer after rounding
        for t in transactions:
            rounded_amount = round(t["amount"], 2)
            self.assertNotEqual(
                0.0,
                rounded_amount,
                msg=f"{t['amount']} is equal to zero after rounding",
            )

    def test_export(self):
        self.post_project("raclette")

        # add members
        self.client.post("/raclette/members/add", data={"name": "zorglub", "weight": 2})
        self.client.post("/raclette/members/add", data={"name": "fred"})
        self.client.post("/raclette/members/add", data={"name": "tata"})
        self.client.post("/raclette/members/add", data={"name": "pépé"})

        # create bills
        self.client.post(
            "/raclette/add",
            data={
                "date": "2016-12-31",
                "what": "fromage à raclette",
                "payer": 1,
                "payed_for": [1, 2, 3, 4],
                "amount": "10.0",
                "original_currency": "USD",
            },
        )

        self.client.post(
            "/raclette/add",
            data={
                "date": "2016-12-31",
                "what": "red wine",
                "payer": 2,
                "payed_for": [1, 3],
                "amount": "200",
                "original_currency": "USD",
            },
        )

        self.client.post(
            "/raclette/add",
            data={
                "date": "2017-01-01",
                "what": "refund",
                "payer": 3,
                "payed_for": [2],
                "amount": "13.33",
                "original_currency": "USD",
            },
        )

        # generate json export of bills
        resp = self.client.get("/raclette/export/bills.json")
        expected = [
            {
                "date": "2017-01-01",
                "what": "refund",
                "amount": 13.33,
                "payer_name": "tata",
                "payer_weight": 1.0,
                "owers": ["fred"],
            },
            {
                "date": "2016-12-31",
                "what": "red wine",
                "amount": 200.0,
                "payer_name": "fred",
                "payer_weight": 1.0,
                "owers": ["zorglub", "tata"],
            },
            {
                "date": "2016-12-31",
                "what": "fromage \xe0 raclette",
                "amount": 10.0,
                "payer_name": "zorglub",
                "payer_weight": 2.0,
                "owers": ["zorglub", "fred", "tata", "p\xe9p\xe9"],
            },
        ]
        self.assertEqual(json.loads(resp.data.decode("utf-8")), expected)

        # generate csv export of bills
        resp = self.client.get("/raclette/export/bills.csv")
        expected = [
            "date,what,amount,payer_name,payer_weight,owers",
            "2017-01-01,refund,13.33,tata,1.0,fred",
            '2016-12-31,red wine,200.0,fred,1.0,"zorglub, tata"',
            '2016-12-31,fromage à raclette,10.0,zorglub,2.0,"zorglub, fred, tata, pépé"',
        ]
        received_lines = resp.data.decode("utf-8").split("\n")

        for i, line in enumerate(expected):
            self.assertEqual(
                set(line.split(",")), set(received_lines[i].strip("\r").split(","))
            )

        # generate json export of transactions
        resp = self.client.get("/raclette/export/transactions.json")
        expected = [
            {"amount": 2.00, "receiver": "fred", "ower": "p\xe9p\xe9"},
            {"amount": 55.34, "receiver": "fred", "ower": "tata"},
            {"amount": 127.33, "receiver": "fred", "ower": "zorglub"},
        ]

        self.assertEqual(json.loads(resp.data.decode("utf-8")), expected)

        # generate csv export of transactions
        resp = self.client.get("/raclette/export/transactions.csv")

        expected = [
            "amount,receiver,ower",
            "2.0,fred,pépé",
            "55.34,fred,tata",
            "127.33,fred,zorglub",
        ]
        received_lines = resp.data.decode("utf-8").split("\n")

        for i, line in enumerate(expected):
            self.assertEqual(
                set(line.split(",")), set(received_lines[i].strip("\r").split(","))
            )

        # wrong export_format should return a 404
        resp = self.client.get("/raclette/export/transactions.wrong")
        self.assertEqual(resp.status_code, 404)

    def test_import_new_project(self):
        # Import JSON in an empty project

        self.post_project("raclette")
        self.login("raclette")

        project = models.Project.query.get("raclette")

        json_to_import = [
            {
                "date": "2017-01-01",
                "what": "refund",
                "amount": 13.33,
                "payer_name": "tata",
                "payer_weight": 1.0,
                "owers": ["fred"],
            },
            {
                "date": "2016-12-31",
                "what": "red wine",
                "amount": 200.0,
                "payer_name": "fred",
                "payer_weight": 1.0,
                "owers": ["zorglub", "tata"],
            },
            {
                "date": "2016-12-31",
                "what": "fromage a raclette",
                "amount": 10.0,
                "payer_name": "zorglub",
                "payer_weight": 2.0,
                "owers": ["zorglub", "fred", "tata", "pepe"],
            },
        ]

        from ihatemoney.web import import_project

        file = io.StringIO()
        json.dump(json_to_import, file)
        file.seek(0)
        import_project(file, project)

        bills = project.get_pretty_bills()

        # Check if all bills has been add
        self.assertEqual(len(bills), len(json_to_import))

        # Check if name of bills are ok
        b = [e["what"] for e in bills]
        b.sort()
        ref = [e["what"] for e in json_to_import]
        ref.sort()

        self.assertEqual(b, ref)

        # Check if other informations in bill are ok
        for i in json_to_import:
            for j in bills:
                if j["what"] == i["what"]:
                    self.assertEqual(j["payer_name"], i["payer_name"])
                    self.assertEqual(j["amount"], i["amount"])
                    self.assertEqual(j["payer_weight"], i["payer_weight"])
                    self.assertEqual(j["date"], i["date"])

                    list_project = [ower for ower in j["owers"]]
                    list_project.sort()
                    list_json = [ower for ower in i["owers"]]
                    list_json.sort()

                    self.assertEqual(list_project, list_json)

    def test_import_partial_project(self):
        # Import a JSON in a project with already existing data

        self.post_project("raclette")
        self.login("raclette")

        project = models.Project.query.get("raclette")

        self.client.post("/raclette/members/add", data={"name": "zorglub", "weight": 2})
        self.client.post("/raclette/members/add", data={"name": "fred"})
        self.client.post("/raclette/members/add", data={"name": "tata"})
        self.client.post(
            "/raclette/add",
            data={
                "date": "2016-12-31",
                "what": "red wine",
                "payer": 2,
                "payed_for": [1, 3],
                "amount": "200",
            },
        )

        json_to_import = [
            {
                "date": "2017-01-01",
                "what": "refund",
                "amount": 13.33,
                "payer_name": "tata",
                "payer_weight": 1.0,
                "owers": ["fred"],
            },
            {  # This expense does not have to be present twice.
                "date": "2016-12-31",
                "what": "red wine",
                "amount": 200.0,
                "payer_name": "fred",
                "payer_weight": 1.0,
                "owers": ["zorglub", "tata"],
            },
            {
                "date": "2016-12-31",
                "what": "fromage a raclette",
                "amount": 10.0,
                "payer_name": "zorglub",
                "payer_weight": 2.0,
                "owers": ["zorglub", "fred", "tata", "pepe"],
            },
        ]

        from ihatemoney.web import import_project

        file = io.StringIO()
        json.dump(json_to_import, file)
        file.seek(0)
        import_project(file, project)

        bills = project.get_pretty_bills()

        # Check if all bills has been add
        self.assertEqual(len(bills), len(json_to_import))

        # Check if name of bills are ok
        b = [e["what"] for e in bills]
        b.sort()
        ref = [e["what"] for e in json_to_import]
        ref.sort()

        self.assertEqual(b, ref)

        # Check if other informations in bill are ok
        for i in json_to_import:
            for j in bills:
                if j["what"] == i["what"]:
                    self.assertEqual(j["payer_name"], i["payer_name"])
                    self.assertEqual(j["amount"], i["amount"])
                    self.assertEqual(j["payer_weight"], i["payer_weight"])
                    self.assertEqual(j["date"], i["date"])

                    list_project = [ower for ower in j["owers"]]
                    list_project.sort()
                    list_json = [ower for ower in i["owers"]]
                    list_json.sort()

                    self.assertEqual(list_project, list_json)

    def test_import_wrong_json(self):
        self.post_project("raclette")
        self.login("raclette")

        project = models.Project.query.get("raclette")

        json_1 = [
            {  # wrong keys
                "checked": False,
                "dimensions": {"width": 5, "height": 10},
                "id": 1,
                "name": "A green door",
                "price": 12.5,
                "tags": ["home", "green"],
            }
        ]

        json_2 = [
            {  # amount missing
                "date": "2017-01-01",
                "what": "refund",
                "payer_name": "tata",
                "payer_weight": 1.0,
                "owers": ["fred"],
            }
        ]

        from ihatemoney.web import import_project

        try:
            file = io.StringIO()
            json.dump(json_1, file)
            file.seek(0)
            import_project(file, project)
        except ValueError:
            self.assertTrue(True)
        except Exception:
            self.fail("unexpected exception raised")
        else:
            self.fail("ExpectedException not raised")

        try:
            file = io.StringIO()
            json.dump(json_2, file)
            file.seek(0)
            import_project(file, project)
        except ValueError:
            self.assertTrue(True)
        except Exception:
            self.fail("unexpected exception raised")
        else:
            self.fail("ExpectedException not raised")

    def test_access_other_projects(self):
        """Test that accessing or editing bills and members from another project fails"""
        # Create project
        self.post_project("raclette")

        # Add members
        self.client.post("/raclette/members/add", data={"name": "zorglub", "weight": 2})
        self.client.post("/raclette/members/add", data={"name": "fred"})
        self.client.post("/raclette/members/add", data={"name": "tata"})
        self.client.post("/raclette/members/add", data={"name": "pépé"})

        # Create bill
        self.client.post(
            "/raclette/add",
            data={
                "date": "2016-12-31",
                "what": "fromage à raclette",
                "payer": 1,
                "payed_for": [1, 2, 3, 4],
                "amount": "10.0",
            },
        )
        # Ensure it has been created
        raclette = models.Project.query.get("raclette")
        self.assertEqual(raclette.get_bills().count(), 1)

        # Log out
        self.client.get("/exit")

        # Create and log in as another project
        self.post_project("tartiflette")

        modified_bill = {
            "date": "2018-12-31",
            "what": "roblochon",
            "payer": 2,
            "payed_for": [1, 3, 4],
            "amount": "100.0",
        }
        # Try to access bill of another project
        resp = self.client.get("/raclette/edit/1")
        self.assertStatus(303, resp)
        # Try to access bill of another project by ID
        resp = self.client.get("/tartiflette/edit/1")
        self.assertStatus(404, resp)
        # Try to edit bill
        resp = self.client.post("/raclette/edit/1", data=modified_bill)
        self.assertStatus(303, resp)
        # Try to edit bill by ID
        resp = self.client.post("/tartiflette/edit/1", data=modified_bill)
        self.assertStatus(404, resp)
        # Try to delete bill
        resp = self.client.get("/raclette/delete/1")
        self.assertStatus(303, resp)
        # Try to delete bill by ID
        resp = self.client.get("/tartiflette/delete/1")
        self.assertStatus(302, resp)

        # Additional check that the bill was indeed not modified or deleted
        bill = models.Bill.query.filter(models.Bill.id == 1).one()
        self.assertEqual(bill.what, "fromage à raclette")

        # Use the correct credentials to modify and delete the bill.
        # This ensures that modifying and deleting the bill can actually work

        self.client.get("/exit")
        self.client.post(
            "/authenticate", data={"id": "raclette", "password": "raclette"}
        )
        self.client.post("/raclette/edit/1", data=modified_bill)
        bill = models.Bill.query.filter(models.Bill.id == 1).one_or_none()
        self.assertNotEqual(bill, None, "bill not found")
        self.assertEqual(bill.what, "roblochon")
        self.client.get("/raclette/delete/1")
        bill = models.Bill.query.filter(models.Bill.id == 1).one_or_none()
        self.assertEqual(bill, None)

        # Switch back to the second project
        self.client.get("/exit")
        self.client.post(
            "/authenticate", data={"id": "tartiflette", "password": "tartiflette"}
        )
        modified_member = {
            "name": "bulgroz",
            "weight": 42,
        }
        # Try to access member from another project
        resp = self.client.get("/raclette/members/1/edit")
        self.assertStatus(303, resp)
        # Try to access member by ID
        resp = self.client.get("/tartiflette/members/1/edit")
        self.assertStatus(404, resp)
        # Try to edit member
        resp = self.client.post("/raclette/members/1/edit", data=modified_member)
        self.assertStatus(303, resp)
        # Try to edit member by ID
        resp = self.client.post("/tartiflette/members/1/edit", data=modified_member)
        self.assertStatus(404, resp)
        # Try to delete member
        resp = self.client.post("/raclette/members/1/delete")
        self.assertStatus(303, resp)
        # Try to delete member by ID
        resp = self.client.post("/tartiflette/members/1/delete")
        self.assertStatus(302, resp)

        # Additional check that the member was indeed not modified or deleted
        member = models.Person.query.filter(models.Person.id == 1).one_or_none()
        self.assertNotEqual(member, None, "member not found")
        self.assertEqual(member.name, "zorglub")
        self.assertTrue(member.activated)

        # Use the correct credentials to modify and delete the member.
        # This ensures that modifying and deleting the member can actually work
        self.client.get("/exit")
        self.client.post(
            "/authenticate", data={"id": "raclette", "password": "raclette"}
        )
        self.client.post("/raclette/members/1/edit", data=modified_member)
        member = models.Person.query.filter(models.Person.id == 1).one()
        self.assertEqual(member.name, "bulgroz")
        self.client.post("/raclette/members/1/delete")
        member = models.Person.query.filter(models.Person.id == 1).one_or_none()
        self.assertEqual(member, None)

    def test_currency_switch(self):

        mock_data = {"USD": 1, "EUR": 0.8, "CAD": 1.2}
        converter = CurrencyConverter()
        converter.get_rates = MagicMock(return_value=mock_data)

        # A project should be editable
        self.post_project("raclette")

        # add members
        self.client.post("/raclette/members/add", data={"name": "zorglub"})
        self.client.post("/raclette/members/add", data={"name": "fred"})
        self.client.post("/raclette/members/add", data={"name": "tata"})

        # create bills
        self.client.post(
            "/raclette/add",
            data={
                "date": "2016-12-31",
                "what": "fromage à raclette",
                "payer": 1,
                "payed_for": [1, 2, 3],
                "amount": "10.0",
            },
        )

        self.client.post(
            "/raclette/add",
            data={
                "date": "2016-12-31",
                "what": "red wine",
                "payer": 2,
                "payed_for": [1, 3],
                "amount": "20",
            },
        )

        self.client.post(
            "/raclette/add",
            data={
                "date": "2017-01-01",
                "what": "refund",
                "payer": 3,
                "payed_for": [2],
                "amount": "13.33",
            },
        )

        project = models.Project.query.get("raclette")

        # First, no currency
        project.switch_currency(CurrencyConverter.no_currency)
        bills = project.get_bills()
        for bill in bills:
            self.assertEqual(bill.original_currency, CurrencyConverter.no_currency)

        # Switch to USD.
        project.switch_currency("USD")
        bills = project.get_bills()
        for bill in bills:
            self.assertEqual(bill.original_currency, "USD")

        # Add bill in EUR.
        self.client.post(
            "/raclette/add",
            data={
                "date": "2017-01-01",
                "what": "other country",
                "payer": 3,
                "payed_for": [2],
                "amount": "13",
                "original_currency": "EUR",
            },
        )

        # Add one bill in CAD.
        self.client.post(
            "/raclette/add",
            data={
                "date": "2017-01-01",
                "what": "other country",
                "payer": 3,
                "payed_for": [2],
                "amount": "10",
                "original_currency": "CAD",
            },
        )

        # Check that the amount is entered as 10CAD and converted to USD.
        assert project.get_bills().first().converted_amount == 8.33

        # If we switch back to CAD.
        project.switch_currency("CAD")
        converted = [
            (b.amount, b.original_currency, b.converted_amount)
            for b in project.get_bills()
        ]

        assert converted == [
            (10.0, "CAD", 10.0),
            (13.0, "EUR", 19.5),
            (13.33, "USD", 16.0),
            (20.0, "USD", 24.0),
            (10.0, "USD", 12.0),
        ]


if __name__ == "__main__":
    unittest.main()
