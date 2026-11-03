from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings

from core.models import UserEmailVerification


class EmailVerificationFlowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="verify_email_user",
            email="verify@example.test",
        )

    @override_settings(
        MAILERS={
            "default": {
                "BACKEND": "django.core.mail.backends.locmem.EmailBackend",
            },
        }
    )
    def test_authenticated_user_requests_and_confirms_one_time_link(self):
        self.client.force_login(self.user)
        response = self.client.post("/api/account/email-verification/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["sent"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["verify@example.test"])

        link = next(
            part for part in mail.outbox[0].body.split()
            if part.startswith("http://testserver/")
        )
        parsed = urlsplit(link)
        token = parse_qs(parsed.query)["token"][0]
        confirm_path = parsed.path

        # Opening the link displays confirmation but does not consume the token.
        response = self.client.get(link)
        self.assertEqual(response.status_code, 200)
        verification = UserEmailVerification.objects.get(user=self.user)
        self.assertIsNone(verification.verified_at)

        response = self.client.post(confirm_path, {"token": token})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["verified"])
        verification.refresh_from_db()
        self.assertIsNotNone(verification.verified_at)
        self.assertEqual(verification.token_digest, "")

        response = self.client.post(confirm_path, {"token": token})
        self.assertEqual(response.status_code, 400)

    @override_settings(
        MAILERS={
            "default": {
                "BACKEND": "django.core.mail.backends.locmem.EmailBackend",
            },
        }
    )
    def test_confirmation_token_expires(self):
        self.client.force_login(self.user)
        self.client.post("/api/account/email-verification/")
        link = next(
            part for part in mail.outbox[0].body.split()
            if part.startswith("http://testserver/")
        )
        parsed = urlsplit(link)
        token = parse_qs(parsed.query)["token"][0]

        verification = UserEmailVerification.objects.get(user=self.user)
        verification.expires_at = verification.created_at
        verification.save(update_fields=["expires_at", "updated_at"])

        response = self.client.post(parsed.path, {"token": token})
        self.assertEqual(response.status_code, 400)
        verification.refresh_from_db()
        self.assertIsNone(verification.verified_at)

    def test_email_change_invalidates_a_pending_link(self):
        with override_settings(
            MAILERS={
                "default": {
                    "BACKEND": "django.core.mail.backends.locmem.EmailBackend",
                },
            }
        ):
            self.client.force_login(self.user)
            self.client.post("/api/account/email-verification/")
            link = next(
                part for part in mail.outbox[0].body.split()
                if part.startswith("http://testserver/")
            )
        parsed = urlsplit(link)
        token = parse_qs(parsed.query)["token"][0]

        self.user.email = "changed@example.test"
        self.user.save(update_fields=["email"])
        response = self.client.post(parsed.path, {"token": token})

        self.assertEqual(response.status_code, 400)
