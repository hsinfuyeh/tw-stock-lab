import unittest
from datetime import datetime, timezone
from marketlab.social import identify, build_social
from marketlab.social_collect import parse_ptt_article, parse_ptt_index, collect_threads


class SocialTests(unittest.TestCase):
    def setUp(self):
        self.stocks = [dict(symbol='2330',name='台積電'),dict(symbol='2317',name='鴻海'),dict(symbol='1101',name='台泥')]
        self.now = datetime(2026,9,29,12,tzinfo=timezone.utc)

    def test_mentions_require_stock_context_and_do_not_count_price_or_partial_code(self):
        self.assertEqual(identify('臺積電與鴻海展望',self.stocks),['2317','2330'])
        self.assertEqual(identify('23301 元，花費2330元',self.stocks),[])
        self.assertEqual(identify('股票2330及2317，2330',self.stocks),['2317','2330'])
        self.assertEqual(identify('2026/11/01',self.stocks),[])
        self.assertEqual(identify('股票市值 2330.50 元，部位2317張',self.stocks),[])

    def test_common_words_require_specific_company_evidence(self):
        stocks=self.stocks+[dict(symbol='3167',name='大量'),dict(symbol='9907',name='統一實'),
            dict(symbol='1216',name='統一'),dict(symbol='2498',name='宏達電'),dict(symbol='2497',name='怡利電')]
        for text in ['台積電大量買超，投資人買進大量股票','台股採用全新材料，大量資源排擠',
                     '股票研究要精確預估，統一資料格式','台積電新聞由聯合報整理','統一實營收成長']:
            self.assertNotIn('3167',identify(text,stocks))
            self.assertNotIn('1216',identify(text,stocks))
        self.assertEqual(identify('大量股價漲停，3167',stocks),['3167'])
        self.assertEqual(identify('[標的] 大量，營收成長',stocks),['3167'])
        self.assertEqual(identify('統一營收及台積電展望',stocks),['1216','2330'])
        self.assertEqual(identify('股票3167',stocks),['3167'])

    def test_generic_financial_language_is_not_a_company_mention(self):
        stocks=[dict(symbol='9921',name='巨大'),dict(symbol='9937',name='全國'),dict(symbol='8201',name='無敵'),dict(symbol='8112',name='至上')]
        self.assertEqual(identify('台股出現巨大波動，全國投資人都在關注，股票策略無敵，風險管理至上',stocks),[])
        self.assertEqual(identify('巨大營收下滑，全國股價穩定',stocks),['9921','9937'])

    def test_disabled_dcard_is_not_requested_and_old_mentions_are_rebuilt(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from social_update import update_social
        values={'social_posts':[dict(source='ptt',id='old',published_at='2026-09-29T11:00:00Z',symbols=['2330'])]}
        store=SimpleNamespace(snapshot=lambda:{'rows':self.stocks},get=lambda key,default=None:values.get(key,default),put=lambda key,value:values.update({key:value}))
        new=dict(source='ptt',id='new',published_at='2026-09-29T11:00:00Z',symbols=['2330'])
        with patch('social_update.collect_ptt',return_value=([new],dict(status='partial',scanned=1))), \
             patch('social_update.collect_threads',return_value=([],dict(status='not_configured',scanned=0))), \
             patch('social_update.collect_dcard') as dcard:
            report=update_social(SimpleNamespace(store=store),self.now,skip_dcard=True)
        dcard.assert_not_called()
        self.assertEqual(report['sources']['dcard']['status'],'disabled')
        self.assertEqual(report['windows']['24h'][0]['total'],1)
        self.assertEqual(report['windows']['24h'][0]['evidence'][0]['id'],'new')
        self.assertIn('重新收集',report['coverage_note'])

    def test_current_identifier_keeps_previous_verified_posts(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from social_update import update_social
        from marketlab.social import IDENTIFIER_VERSION
        previous=dict(source='ptt',id='verified',published_at='2026-09-29T11:00:00Z',symbols=['2330'])
        values={'social_observations':dict(posts=[previous],identifier_version=IDENTIFIER_VERSION,rebuild_at='2026-09-28T11:00:00Z')}
        store=SimpleNamespace(snapshot=lambda:{'rows':self.stocks},get=lambda key,default=None:values.get(key,default),put=lambda key,value:values.update({key:value}))
        with patch('social_update.collect_ptt',return_value=([],dict(status='partial',scanned=0))), \
             patch('social_update.collect_threads',return_value=([],dict(status='not_configured',scanned=0))):
            report=update_social(SimpleNamespace(store=store),self.now,skip_dcard=True)
        self.assertEqual(report['windows']['24h'][0]['total'],1)
        self.assertEqual(values['social_observations']['rebuild_at'],'2026-09-28T11:00:00Z')

    def test_deduplication_time_windows_and_missing_source(self):
        post=dict(source='ptt',id='a',published_at='2026-09-29T11:00:00+00:00',symbols=['2330','2330'],url='https://www.ptt.cc/bbs/Stock/M.1.html',title='台積電')
        older=dict(post,id='b',published_at='2026-09-27T11:00:00+00:00')
        future=dict(post,id='c',published_at='2026-09-30T11:00:00+00:00')
        data=build_social([post,post,older,future],self.stocks,{'ptt':{'status':'partial'},'dcard':{'status':'failed'},'threads':{'status':'not_configured'}},self.now)
        row=data['windows']['24h'][0]
        self.assertEqual(row['counts'],{'ptt':1,'dcard':None,'threads':None})
        self.assertEqual(row['total'],1)
        self.assertEqual(data['windows']['7d'][0]['total'],2)
        self.assertEqual(len(row['evidence']),1)

    def test_html_parser_uses_publication_year_and_excludes_replies(self):
        html='<div id="main-content"><div class="article-metaline"><span class="article-meta-value">a</span></div><span class="article-meta-value">Stock</span><span class="article-meta-value">[標的] 台積電</span><span class="article-meta-value">Mon Sep 28 20:10:00 2026</span>股票2330<div class="push">鴻海2317</div></div>'
        post=parse_ptt_article(html,'https://www.ptt.cc/bbs/Stock/M.1.html',self.stocks)
        self.assertEqual(post['symbols'],['2330'])
        self.assertEqual(post['published_at'],'2026-09-28T20:10:00+08:00')
        self.assertNotIn('text',post)
        links,prev=parse_ptt_index('<a href="/bbs/Stock/M.1.html">a</a><a href="/bbs/Stock/index2.html">‹ 上頁</a>')
        self.assertEqual(links,['https://www.ptt.cc/bbs/Stock/M.1.html'])
        self.assertEqual(prev,'https://www.ptt.cc/bbs/Stock/index2.html')

    def test_author_name_and_quoted_text_are_not_mentions(self):
        html='<div id="main-content"><span class="article-meta-value">abc (台積電員工)</span><span class="article-meta-value">Stock</span><span class="article-meta-value">[心得] 心情</span><span class="article-meta-value">Mon Sep 28 20:10:00 2026</span>\n生活開心\n&gt; 鴻海股價2317\n</div>'
        post=parse_ptt_article(html,'https://www.ptt.cc/bbs/Stock/M.1.html',self.stocks)
        self.assertEqual(post['symbols'],[])

    def test_dcard_failure_and_threads_token_never_reach_public_status(self):
        from urllib.error import HTTPError
        from marketlab.social_collect import collect_dcard
        def fail(url,**kwargs): raise HTTPError(url,403,'secret-from-provider',None,None)
        posts,status=collect_dcard(self.stocks,self.now,fetch=fail)
        self.assertEqual(status['status'],'failed')
        self.assertEqual(status['error'],'HTTP 403')
        posts,status=collect_threads(self.stocks,self.now,token='secret-token',fetch=fail)
        self.assertEqual(status['error'],'HTTP 403')
        self.assertNotIn('secret',str(status))

    def test_missing_threads_token_never_makes_request(self):
        def fail(*args,**kwargs): raise AssertionError('unexpected request')
        posts,status=collect_threads(self.stocks,self.now,token='',fetch=fail)
        self.assertEqual(posts,[])
        self.assertEqual(status['status'],'not_configured')

    def test_authorized_threads_uses_header_and_bounds_public_evidence(self):
        import json
        from urllib.parse import parse_qs,urlparse
        calls=[]
        def fetch(url,headers):
            calls.append((url,headers))
            return json.dumps({'data':[dict(id='t1',text='台積電股價展望',timestamp='2026-09-29T11:00:00Z',permalink='https://www.threads.com/@a/post/abc')]})
        posts,status=collect_threads(self.stocks,self.now,token='private-token',fetch=fetch)
        self.assertEqual(len(calls),3)
        self.assertTrue(all('private-token' not in url for url,_ in calls))
        self.assertEqual(calls[0][1]['Authorization'],'Bearer private-token')
        self.assertEqual(posts[0]['symbols'],['2330'])
        self.assertNotIn('private-token',str(posts)+str(status))
        self.assertEqual(parse_qs(urlparse(calls[0][0]).query)['search_type'],['RECENT'])

    def test_dcard_title_excerpt_and_publication_window(self):
        import json
        from marketlab.social_collect import collect_dcard
        def fetch(url): return json.dumps([dict(id=123,title='台積電',excerpt='股票2330',createdAt='2026-09-29T11:00:00Z'),dict(id=122,title='鴻海',createdAt='2026-09-01T11:00:00Z')])
        posts,status=collect_dcard(self.stocks,self.now,fetch=fetch)
        self.assertEqual(len(posts),1)
        self.assertEqual(posts[0]['url'],'https://www.dcard.tw/f/stock/p/123')
        self.assertEqual(status['pages'],1)


if __name__=='__main__': unittest.main()
