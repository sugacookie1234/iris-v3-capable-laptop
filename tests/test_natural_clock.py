from datetime import datetime, timezone
import json
import unittest
from iris.desktop.local_time import response
from iris.desktop.server import voice_request

class NaturalClockTests(unittest.TestCase):
    def test_display_and_actual_speech_payload_agree(self):
        result=response('What time is it in Montreal?', 'UTC', datetime(2026,11,4,0,7,tzinfo=timezone.utc))
        self.assertIn('19:07 on Tuesday, November 3, 2026',result['reply'])
        self.assertIn('seven oh seven PM',result['spoken_reply'])
        self.assertIn('November third',result['spoken_reply'])
        self.assertIn('Eastern Standard Time',result['spoken_reply'])
        payload=json.loads(voice_request({'IRIS_FISH_API_KEY':'synthetic'},result['spoken_reply']).data)
        self.assertEqual(payload['text'],result['spoken_reply'])
        self.assertNotIn('America/',payload['text'])
    def test_dst_and_midnight(self):
        result=response('What time is it in Montreal?', 'UTC', datetime(2026,7,4,4,0,tzinfo=timezone.utc))
        self.assertIn('midnight',result['spoken_reply'])
        self.assertIn('Eastern Daylight Time',result['spoken_reply'])
    def test_natural_queries_are_bounded(self):
        for text in ['Iris, can you tell me what time it is?', "What's the time right now?", 'Do you know the current time?', 'Tell me the time, please.']:
            self.assertIsNotNone(response(text,'UTC'),text)
        for text in ['What time was it yesterday?', 'Set a meeting at 19:07', 'Convert 19:07 to Tokyo time', 'Do not tell me the time']:
            self.assertIsNone(response(text,'UTC'),text)
    def test_date_ordinals(self):
        for day,word in [(1,'first'),(3,'third'),(21,'twenty-first'),(31,'thirty-first')]:
            result=response("What's today's date?",'UTC',datetime(2026,3,day,tzinfo=timezone.utc))
            self.assertIn(word,result['spoken_reply'])
            self.assertIn('twenty twenty-six',result['spoken_reply'])
