import csv,io,json,math,unittest,zipfile
from pathlib import Path
from biology.build_measured import summarize

class MeasuredBiology(unittest.TestCase):
    def archive(self,quantities=('1','3')):
        rows=[]
        for i,n in enumerate(quantities):rows.append(dict(id=str(i),occurrenceID='study:sample:ASV_'+str(i),organismQuantityType='DNA sequence reads',organismQuantity=n,eventID='study:sample',eventDate='2016-06-07',decimalLatitude='59.8',decimalLongitude='17.6',coordinateUncertaintyInMeters='',minimumDepthInMeters='0',maximumDepthInMeters='.1',materialSampleID='https://example.org/sample',kingdom='Fungi',samplingProtocol='Test protocol'))
        def tab(rows,fields):
            s=io.StringIO();w=csv.DictWriter(s,fieldnames=fields,delimiter='\t');w.writeheader();w.writerows(rows);return s.getvalue()
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:
            z.writestr('occurrence.txt',tab(rows,list(rows[0])))
            z.writestr('extendedmeasurementorfact.txt',tab([dict(id=str(i),measurementType='water content',measurementValue='.8',measurementUnit='g/g') for i in range(len(rows))],['id','measurementType','measurementValue','measurementUnit']))
        return b.getvalue()
    def test_metrics(self):
        s=summarize(self.archive())['samples'][0]
        self.assertEqual(s['asv_richness'],2);self.assertEqual(s['sequence_reads'],4)
        self.assertAlmostEqual(s['shannon_reads'],-.25*math.log(.25)-.75*math.log(.75),places=6)
        self.assertEqual(s['gravimetric_water_g_g'],.8);self.assertIsNone(s['coordinate_uncertainty_m'])
    def test_bad_read_counts(self):
        for v in ('nan','-1','0'):
            with self.assertRaises(ValueError):summarize(self.archive((v,'1')))
    def test_published_coverage(self):
        d=json.loads((Path(__file__).resolve().parents[2]/'frontend/static/data/biology/kungsangen.json').read_text())
        self.assertEqual(d['sample_count'],20);self.assertEqual(d['record_count'],1152)
        self.assertEqual({s['date'] for s in d['samples']},{'2016-06-07'})
        self.assertEqual(len({(s['lat'],s['lon']) for s in d['samples']}),1)
        self.assertEqual(d['kingdoms'],['Fungi']);self.assertEqual(d['license'],'CC0 1.0')
