import unittest
from iris.generalist.visuals import compound, validate

class VisualTests(unittest.TestCase):
    def test_monthly_compounding(self):
        result=validate(compound(1000,12,1,100))
        expected=1000*1.01**12+100*((1.01**12-1)/.01)
        self.assertEqual(result['points'][-1],[1,round(expected,2),2200])
    def test_zero_rate(self):
        self.assertEqual(compound(100,0,2,10)['points'][-1],[2,340,340])
    def test_bad_inputs(self):
        for value in (-1,True,float('nan'),float('inf'),'100'):
            with self.assertRaises(ValueError):compound(value)
    def test_reject_executable_fields_and_bad_points(self):
        spec=compound();spec['script']='alert(1)'
        with self.assertRaises(ValueError):validate(spec)
        spec=compound();spec['points']=[[0,float('nan'),1]]
        with self.assertRaises(ValueError):validate(spec)
