import unittest
from unittest.mock import patch


class SocialCliTests(unittest.TestCase):
    def test_empty_ptt_index_is_not_treated_as_successful_collection(self):
        from datetime import datetime,timezone
        from marketlab.social_collect import collect_ptt
        posts,status=collect_ptt([],datetime(2026,9,30,tzinfo=timezone.utc),fetch=lambda _: '<html><body>no posts</body></html>',max_pages=1)
        self.assertEqual(posts,[])
        self.assertEqual(status['status'],'failed')
    def test_manual_cloud_period_and_anonymous_threads_are_passed_to_collector(self):
        import social_update
        with patch('sys.argv',['social_update.py','--window','24h','--public-threads']), \
             patch.object(social_update,'MarketService') as service, \
             patch.object(social_update,'update_social',return_value={}) as collect, \
             patch.object(social_update,'atomic_json'):
            social_update.main()
        collect.assert_called_once_with(service.return_value,skip_dcard=False,window='24h',local_public=True)


if __name__=='__main__': unittest.main()
