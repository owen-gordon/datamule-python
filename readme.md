## datamule

A python package to make using SEC filings easier. Currently makes downloads easier and faster.

Links to indices:
* [https://www.mediafire.com/file/llo0w2cwerxnooo/filings_index.csv/file](Filings Index) (600mb)
* [https://www.mediafire.com/file/lw9f5igfvjumcla/submissions_index.csv/file](Submissions Index) (400mb)
* [https://www.mediafire.com/file/7r42bx1x8eltf2f/metadata.json/file](Metadata) (60b)
* [https://www.mediafire.com/file/idkhzh0wkm5xgox/company_tickers.csv/file](Company Tickers) (400kb)


Installation
```
pip install datamule
```

## Quickstart:

Either download the pre-built indices from the links in the readme and set the indices_path to the folder
```
from datamule import Downloader
downloader = Downloader()
downloader.set_indices_path(indices_path)
```

Or run the indexer
```
import sec_indexer
sec_index.run()
```

Example Downloads
```
# Example 1: Download all 10-K filings for Tesla using CIK
downloader.download(form='10-K', cik='1318605', output_dir='filings')

# Example 2: Download 10-K filings for Tesla and META using CIK
downloader.download(form='10-K', cik=['1318605','1326801'], output_dir='filings')

# Example 3: Download 10-K filings for Tesla using ticker
downloader.download(form='10-K', ticker='TSLA', output_dir='filings')

# Example 4: Download 10-K filings for Tesla and META using ticker
downloader.download(form='10-K', ticker=['TSLA','META'], output_dir='filings')

# Example 5: Download every form 3 for a specific date
downloader.download(form ='3', date='2024-05-21', output_dir='filings')

# Example 6: Download every 10K for a year
downloader.download(form='10-K', date=('2024-01-01', '2024-12-31'), output_dir='filings')

# Example 7: Download every form 4 for a list of dates
downloader.download(form = '4',date=['2024-01-01', '2024-12-31'], output_dir='filings')
```

Future Features:
* Integration with datamule's SEC Router endpoint for downloading on the fly
* Integration with datamule's SEC Router bulk data endpoint to remove need for indexing.
