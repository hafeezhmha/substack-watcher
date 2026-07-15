import unittest
from unittest.mock import patch

import watch_pintofview
from watch_pintofview import (
    extract_ticket_link,
    extract_ticket_links,
    parse_rss_feed,
    unseen_items,
)


class TicketLinkExtractionTests(unittest.TestCase):
    def test_detects_urbanaut_link_without_ticket_keywords(self):
        html = '<a href="https://urbanaut.app/spot/pint-of-view-lecture">Lecture details</a>'

        self.assertEqual(
            extract_ticket_link(html),
            "https://urbanaut.app/spot/pint-of-view-lecture",
        )

    def test_detects_razorpay_short_link_without_ticket_keywords(self):
        html = '<a href="https://rzp.io/rzp/CB2AfC8">Wednesday lecture</a>'

        self.assertEqual(
            extract_ticket_link(html),
            "https://rzp.io/rzp/CB2AfC8",
        )

    def test_detects_booking_path_for_unlisted_provider(self):
        html = '<a href="https://example.com/bookings/event?id=1375">Bird lecture</a>'

        self.assertEqual(
            extract_ticket_link(html),
            "https://example.com/bookings/event?id=1375",
        )

    def test_uses_anchor_text_when_url_has_no_booking_signal(self):
        html = '<a href="https://tickets.example.com/summer-talk">Book tickets now</a>'

        self.assertEqual(
            extract_ticket_link(html),
            "https://tickets.example.com/summer-talk",
        )

    def test_detects_ticketing_hostname_without_ticket_text(self):
        html = '<a href="https://tickets.example.com/summer-talk">Details</a>'

        self.assertEqual(
            extract_ticket_link(html),
            "https://tickets.example.com/summer-talk",
        )

    def test_prefers_ticket_link_over_an_earlier_image_link(self):
        html = """
            <a href="https://substackcdn.com/poster.jpg"><img src="poster.jpg"></a>
            <a href="https://pages.razorpay.com/pl_123/view">Book tickets</a>
        """

        self.assertEqual(
            extract_ticket_link(html),
            "https://pages.razorpay.com/pl_123/view",
        )

    def test_returns_every_booking_link_once(self):
        html = """
            <a href="https://urbanaut.app/spot/sunday-lecture">Sunday tickets</a>
            <a href="https://puttingscene.com/events/1824">Wednesday tickets</a>
            <a href="https://urbanaut.app/spot/sunday-lecture">Sunday tickets again</a>
        """

        self.assertEqual(
            extract_ticket_links(html),
            [
                "https://urbanaut.app/spot/sunday-lecture",
                "https://puttingscene.com/events/1824",
            ],
        )

    def test_ignores_social_and_internal_links(self):
        html = """
            <a href="https://pintofviewclub.substack.com/p/new-post">Read more</a>
            <a href="https://instagram.com/pintofview">Instagram</a>
        """

        self.assertIsNone(extract_ticket_link(html))


class WatcherReliabilityTests(unittest.TestCase):
    def test_processes_unseen_posts_oldest_first(self):
        items = [
            {"guid": "newest"},
            {"guid": "middle"},
            {"guid": "last-seen"},
        ]

        self.assertEqual(
            [item["guid"] for item in unseen_items(items, "last-seen")],
            ["middle", "newest"],
        )

    def test_delivery_failure_does_not_update_state(self):
        feed = {
            "items": [{"guid": "new", "title": "New post", "pubDate": "today"}]
        }
        with (
            patch.object(watch_pintofview, "load_state", return_value={}),
            patch.object(watch_pintofview, "fetch_feed_json", return_value=feed),
            patch.object(watch_pintofview, "send_email", return_value=False),
            patch.object(watch_pintofview, "save_state") as save_state,
        ):
            self.assertEqual(watch_pintofview.main(), 1)

        save_state.assert_not_called()

    def test_successful_deliveries_advance_state_for_each_post(self):
        feed = {
            "items": [
                {"guid": "newest", "title": "Newest", "pubDate": "today"},
                {"guid": "middle", "title": "Middle", "pubDate": "yesterday"},
                {"guid": "last-seen", "title": "Last", "pubDate": "earlier"},
            ]
        }
        state = {"last_post_id": "last-seen"}
        saved_ids = []

        def record_state(updated_state):
            saved_ids.append(updated_state["last_post_id"])

        with (
            patch.object(watch_pintofview, "load_state", return_value=state),
            patch.object(watch_pintofview, "fetch_feed_json", return_value=feed),
            patch.object(watch_pintofview, "send_email", return_value=True) as send_email,
            patch.object(watch_pintofview, "save_state", side_effect=record_state),
        ):
            self.assertEqual(watch_pintofview.main(), 0)

        self.assertEqual([call.args[0] for call in send_email.call_args_list], ["Middle", "Newest"])
        self.assertEqual(saved_ids, ["middle", "newest"])

    def test_direct_rss_parser_preserves_content(self):
        xml = """<?xml version="1.0"?>
        <rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><item>
          <title>Test</title><link>https://example.com/post</link><guid>post-1</guid>
          <pubDate>today</pubDate><description>Summary</description>
          <content:encoded><![CDATA[<a href="https://example.com/book">Book</a>]]></content:encoded>
        </item></channel></rss>"""

        self.assertEqual(
            parse_rss_feed(xml)["items"][0]["content"],
            '<a href="https://example.com/book">Book</a>',
        )


if __name__ == "__main__":
    unittest.main()
