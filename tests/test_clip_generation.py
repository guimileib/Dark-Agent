import unittest
from unittest.mock import MagicMock, patch
import sys
import os
from pathlib import Path

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

# Mock numpy
mock_np = MagicMock()
sys.modules['numpy'] = mock_np

from core.clip_analyzer import ClipAnalyzer

class TestClipAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = ClipAnalyzer(Path("dummy.mp4"))
        self.analyzer.duracao_total = 1000.0
        self.analyzer.frame_rate = 30.0

    def test_analisar_clips_all_possibilities(self):
        # Mock internal methods to avoid ffmpeg calls
        self.analyzer._detectar_mudancas_cena = MagicMock(return_value=list(range(0, 1000, 10)))
        self.analyzer._analisar_movimento = MagicMock(return_value={i: 0.5 for i in range(1000)})
        self.analyzer._analisar_audio = MagicMock(return_value={i: 0.5 for i in range(1000)})
        self.analyzer._gerar_razoes = MagicMock(return_value=["Razão teste"])
        
        # Mock _calcular_score_clip to return predictable scores
        # We'll make it so that later clips have higher scores to test sorting
        def side_effect_score(inicio, fim, *args):
            return (inicio / 1000.0) # Score increases with start time
        
        self.analyzer._calcular_score_clip = MagicMock(side_effect=side_effect_score)
        
        # Run analysis with max_clips=0 (all possibilities)
        clips = self.analyzer.analisar_clips(duracao_min=10, duracao_max=20, max_clips=0)
        
        # Verify we got clips
        self.assertTrue(len(clips) > 0)
        
        # Verify sorting (descending score)
        scores = [c['score'] for c in clips]
        self.assertEqual(scores, sorted(scores, reverse=True))
        
        # Verify we got more than default 10 (assuming enough duration)
        # With duration 100 and window 10-20, step 5, we should have many clips
        self.assertTrue(len(clips) > 10)
        
        print(f"Generated {len(clips)} clips with max_clips=0")
        print(f"Top score: {clips[0]['score']}")
        print(f"Bottom score: {clips[-1]['score']}")

    def test_analisar_clips_limited(self):
        # Mock internal methods
        self.analyzer._detectar_mudancas_cena = MagicMock(return_value=[10, 20, 30])
        self.analyzer._analisar_movimento = MagicMock(return_value={i: 0.5 for i in range(100)})
        self.analyzer._analisar_audio = MagicMock(return_value={i: 0.5 for i in range(100)})
        self.analyzer._calcular_score_clip = MagicMock(return_value=0.8)
        self.analyzer._gerar_razoes = MagicMock(return_value=["Razão teste"])
        
        # Run analysis with max_clips=5
        clips = self.analyzer.analisar_clips(duracao_min=10, duracao_max=20, max_clips=5)
        
        # Verify limit
        self.assertLessEqual(len(clips), 5)

if __name__ == '__main__':
    unittest.main()
