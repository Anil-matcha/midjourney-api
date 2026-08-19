import unittest
from unittest.mock import Mock

from midjourney_api import MidjourneyAPI


def response_with(payload):
    response = Mock()
    response.json.return_value = payload
    return response


class MidjourneyAPITest(unittest.TestCase):
    def test_v8_posts_current_contract(self):
        session = Mock()
        session.post.return_value = response_with({"request_id": "req_v8", "status": "processing"})
        api = MidjourneyAPI(api_key="test-key", session=session)

        result = api.v8(
            "A cinematic astronaut",
            aspect_ratio="16:9",
            stylize=500,
            chaos=12,
            weird=40,
            image_url="https://example.com/reference.jpg",
            webhook_url="https://example.com/webhook",
        )

        self.assertEqual(result["request_id"], "req_v8")
        session.post.assert_called_once_with(
            "https://api.muapi.ai/api/v1/midjourney-v8",
            json={
                "prompt": "A cinematic astronaut",
                "image_url": "https://example.com/reference.jpg",
                "aspect_ratio": "16:9",
                "stylize": 500,
                "chaos": 12,
                "weird": 40,
                "webhook_url": "https://example.com/webhook",
            },
            headers=api.headers,
            timeout=120,
        )

    def test_v7_and_niji_select_their_endpoints(self):
        session = Mock()
        session.post.return_value = response_with({"request_id": "req", "status": "processing"})
        api = MidjourneyAPI(api_key="test-key", session=session)

        api.v7("A photorealistic portrait")
        api.niji("A manga character")

        self.assertEqual(session.post.call_args_list[0].args[0], "https://api.muapi.ai/api/v1/midjourney-v7")
        self.assertEqual(session.post.call_args_list[1].args[0], "https://api.muapi.ai/api/v1/midjourney-niji")

    def test_generation_rejects_invalid_inputs(self):
        api = MidjourneyAPI(api_key="test-key", session=Mock())

        with self.assertRaises(ValueError):
            api.generate("", model="midjourney-v8")
        with self.assertRaises(ValueError):
            api.generate("A scene", aspect_ratio="4:5")
        with self.assertRaises(ValueError):
            api.generate("A scene", model="midjourney-v6")
        with self.assertRaises(ValueError):
            api.generate("A scene", weird=3001)

    def test_wait_for_completion_polls_until_done(self):
        session = Mock()
        session.get.side_effect = [
            response_with({"request_id": "req", "status": "processing"}),
            response_with(
                {
                    "request_id": "req",
                    "status": "completed",
                    "outputs": ["https://example.com/one.png", "https://example.com/two.png"],
                }
            ),
        ]
        api = MidjourneyAPI(api_key="test-key", session=session)

        result = api.wait_for_completion("req", poll_interval=0, timeout=1)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(api.extract_image_urls(result), ["https://example.com/one.png", "https://example.com/two.png"])
        self.assertEqual(session.get.call_count, 2)

    def test_generate_and_wait_requires_submission_id(self):
        session = Mock()
        session.post.return_value = response_with({"status": "processing"})
        api = MidjourneyAPI(api_key="test-key", session=session)

        with self.assertRaisesRegex(RuntimeError, "No request_id"):
            api.generate_and_wait("A scene", poll_interval=0, timeout=1)


if __name__ == "__main__":
    unittest.main()
