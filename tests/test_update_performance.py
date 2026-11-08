import copy
import unittest
from marketlab.analytics import ResearchModel,event_outcome,HORIZONS
from test_analytics import bars,cal,SETTINGS


class UpdatePerformanceTests(unittest.TestCase):
    def test_supplied_axis_matches_original_for_valid_gaps_and_adjustments(self):
        for issue in ('none','gap','adjustment','locked'):
            rows=bars(85)
            if issue=='gap': rows.pop(43)
            if issue=='adjustment': rows[44]['change']='X'
            if issue=='locked': rows[41].update(high=rows[41]['close'],low=rows[41]['close'])
            calendar=cal(bars(85));axis=[r['date'] for r in rows]
            for horizon in HORIZONS:
                for index in (0,39,40,42,len(rows)-2):
                    with self.subTest(issue=issue,horizon=horizon,index=index):
                        self.assertEqual(event_outcome(rows,index,horizon,SETTINGS,calendar),
                            event_outcome(rows,index,horizon,SETTINGS,calendar,dates=axis))

    def test_model_outcomes_and_estimates_preserve_inputs(self):
        rows=bars(190); original=copy.deepcopy(rows);calendar=cal(rows)
        model=ResearchModel(rows,SETTINGS,calendar)
        for horizon in HORIZONS:
            self.assertEqual(model.outcomes[horizon],[event_outcome(rows,i,horizon,SETTINGS,calendar)
                for i in range(len(rows))])
        self.assertEqual(rows,original)
        self.assertEqual(model._dates,[r['date'] for r in rows])

if __name__=='__main__': unittest.main()
