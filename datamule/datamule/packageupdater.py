import asyncio
import aiohttp
import json
import csv
import os
from pkg_resources import resource_filename
from tqdm import tqdm
from .helper import headers
from .downloader import PreciseRateLimiter, RateMonitor

class PackageUpdater:
    def __init__(self):
        self.limiter = PreciseRateLimiter(5)  # 5 requests per second
        self.rate_monitor = RateMonitor()
        self.headers = headers
        self.timeout = aiohttp.ClientTimeout(total=30)  # 30 second timeout
        self.max_retries = 3
    
    async def _fetch_json(self, session, url, retry_count=0):
        """Fetch JSON with rate limiting and monitoring."""
        async with self.limiter:
            try:
                tqdm.write(f"Fetching {url}")
                async with session.get(url, timeout=self.timeout) as response:
                    response.raise_for_status()
                    tqdm.write(f"Reading content from {url}")
                    content = await response.read()
                    await self.rate_monitor.add_request(len(content))
                    tqdm.write(f"Parsing JSON from {url}")
                    return await response.json()
            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                if retry_count < self.max_retries:
                    tqdm.write(f"Retry {retry_count + 1} for {url} after error: {str(e)}")
                    await asyncio.sleep(1 * (retry_count + 1))  # Exponential backoff
                    return await self._fetch_json(session, url, retry_count + 1)
                tqdm.write(f"Failed after {self.max_retries} retries for {url}: {str(e)}")
                return None
            except Exception as e:
                tqdm.write(f"Error fetching {url}: {str(e)}")
                return None

    async def _update_company_tickers(self):
        """Update company tickers data files."""
        url = 'https://www.sec.gov/files/company_tickers.json'
        
        # Define file paths
        json_file = resource_filename('datamule', 'data/company_tickers.json')
        csv_file = resource_filename('datamule', 'data/company_tickers.csv')
        
        # Define temporary file paths
        temp_json_file = json_file + '.temp'
        temp_csv_file = csv_file + '.temp'

        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                data = await self._fetch_json(session, url)
                if not data:
                    raise Exception("Failed to fetch company tickers data")

                # Save the raw JSON file
                with open(temp_json_file, 'w') as f:
                    json.dump(data, f, indent=4)
                
                # Convert to CSV
                with open(temp_csv_file, 'w', newline='') as csvfile:
                    fieldnames = ['cik', 'ticker', 'title']
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    for _, company in data.items():
                        writer.writerow({
                            'cik': str(company['cik_str']).zfill(10),
                            'ticker': company['ticker'],
                            'title': company['title']
                        })

                # Replace original files
                for src, dst in [(temp_json_file, json_file), (temp_csv_file, csv_file)]:
                    if os.path.exists(dst):
                        os.remove(dst)
                    os.rename(src, dst)

                print(f"Company tickers successfully updated")
                return True

            except Exception as e:
                print(f"Error updating company tickers: {str(e)}")
                return False
            
            finally:
                # Clean up temp files
                for temp_file in [temp_json_file, temp_csv_file]:
                    if os.path.exists(temp_file):
                        try:
                            os.remove(temp_file)
                        except Exception as e:
                            print(f"Warning: Could not remove {temp_file}: {str(e)}")

    async def _process_metadata_batch(self, session, companies, metadata_writer, former_names_writer):
        """Process a batch of companies for metadata updates."""
        metadata_fields = [
            'cik', 'name', 'entityType', 'sic', 'sicDescription', 'ownerOrg',
            'insiderTransactionForOwnerExists', 'insiderTransactionForIssuerExists',
            'tickers', 'exchanges', 'ein', 'description', 'website', 'investorWebsite',
            'category', 'fiscalYearEnd', 'stateOfIncorporation', 'stateOfIncorporationDescription',
            'phone', 'flags', 'mailing_street1', 'mailing_street2', 'mailing_city',
            'mailing_stateOrCountry', 'mailing_zipCode', 'mailing_stateOrCountryDescription',
            'business_street1', 'business_street2', 'business_city', 'business_stateOrCountry',
            'business_zipCode', 'business_stateOrCountryDescription'
        ]

        tqdm.write(f"\nProcessing batch with CIKs: {[company['cik'] for company in companies]}")
        tasks = []
        for company in companies:
            cik = company['cik']
            url = f'https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json'
            tasks.append(self._fetch_json(session, url))

        try:
            tqdm.write("Waiting for batch requests to complete...")
            # Add timeout for the entire batch
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=120  # 2 minute timeout for entire batch
            )
            tqdm.write("Batch requests completed")
        except asyncio.TimeoutError:
            tqdm.write("Batch timeout occurred, processing partial results")
            # Get whatever results we have
            results = [None] * len(tasks)
        except Exception as e:
            tqdm.write(f"Error in gather: {str(e)}")
            return

        tqdm.write("Processing batch results...")
        for company, result in zip(companies, results):
            if isinstance(result, Exception) or not result:
                tqdm.write(f"Error processing CIK {company['cik']}: {str(result) if isinstance(result, Exception) else 'No data'}")
                # Write empty row but preserve CIK
                empty_row = {field: '' for field in metadata_fields}
                empty_row['cik'] = company['cik']
                metadata_writer.writerow(empty_row)
                continue

            try:
                tqdm.write(f"Processing metadata for CIK {company['cik']}")
                metadata = {field: result.get(field, '') for field in metadata_fields if field not in ['tickers', 'exchanges']}
                metadata['cik'] = company['cik']
                metadata['tickers'] = ','.join(result.get('tickers', []) or [])
                metadata['exchanges'] = ','.join(result.get('exchanges', []) or [])

                # Add address information
                for address_type in ['mailing', 'business']:
                    address = result.get('addresses', {}).get(address_type, {})
                    for key, value in address.items():
                        metadata[f'{address_type}_{key}'] = value if value is not None else ''

                metadata_writer.writerow(metadata)

                for former_name in result.get('formerNames', []):
                    if former_name.get('name'):  # Only process if name exists
                        former_names_writer.writerow({
                            'cik': company['cik'],
                            'former_name': former_name['name'],
                            'from_date': former_name.get('from', ''),
                            'to_date': former_name.get('to', '')
                        })
                tqdm.write(f"Completed processing CIK {company['cik']}")

            except Exception as e:
                tqdm.write(f"Error processing metadata for CIK {company['cik']}: {str(e)}")
                # Write empty row but preserve CIK
                empty_row = {field: '' for field in metadata_fields}
                empty_row['cik'] = company['cik']
                metadata_writer.writerow(empty_row)

    async def _update_company_metadata(self):
        """Update company metadata and former names files."""
        metadata_file = resource_filename('datamule', 'data/company_metadata.csv')
        former_names_file = resource_filename('datamule', 'data/company_former_names.csv')
        
        temp_metadata_file = metadata_file + '.temp'
        temp_former_names_file = former_names_file + '.temp'

        # Load current company tickers
        with open(resource_filename('datamule', 'data/company_tickers.csv'), 'r') as f:
            company_tickers = list(csv.DictReader(f))

        metadata_fields = ['cik', 'name', 'entityType', 'sic', 'sicDescription', 'ownerOrg',
                        'insiderTransactionForOwnerExists', 'insiderTransactionForIssuerExists',
                        'tickers', 'exchanges', 'ein', 'description', 'website', 'investorWebsite',
                        'category', 'fiscalYearEnd', 'stateOfIncorporation', 'stateOfIncorporationDescription',
                        'phone', 'flags', 'mailing_street1', 'mailing_street2', 'mailing_city',
                        'mailing_stateOrCountry', 'mailing_zipCode', 'mailing_stateOrCountryDescription',
                        'business_street1', 'business_street2', 'business_city', 'business_stateOrCountry',
                        'business_zipCode', 'business_stateOrCountryDescription']

        former_names_fields = ['cik', 'former_name', 'from_date', 'to_date']

        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                with open(temp_metadata_file, 'w', newline='') as mf, \
                     open(temp_former_names_file, 'w', newline='') as fnf:
                    
                    metadata_writer = csv.DictWriter(mf, fieldnames=metadata_fields)
                    metadata_writer.writeheader()
                    
                    former_names_writer = csv.DictWriter(fnf, fieldnames=former_names_fields)
                    former_names_writer.writeheader()

                    # Process in batches of 10 companies with progress bar
                    batch_size = 10
                    total_companies = len(company_tickers)
                    progress_bar = tqdm(total=total_companies, desc="Processing CIKs")
                    
                    for i in range(0, total_companies, batch_size):
                        batch = company_tickers[i:i + batch_size]
                        await self._process_metadata_batch(
                            session, batch, metadata_writer, former_names_writer
                        )
                        progress_bar.update(len(batch))
                    
                    progress_bar.close()

            # Replace original files
            for src, dst in [(temp_metadata_file, metadata_file), 
                           (temp_former_names_file, former_names_file)]:
                if os.path.exists(dst):
                    os.remove(dst)
                os.rename(src, dst)

            print("Company metadata successfully updated")
            return True

        except Exception as e:
            print(f"Error updating company metadata: {str(e)}")
            return False

        finally:
            # Clean up temp files
            for temp_file in [temp_metadata_file, temp_former_names_file]:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except Exception as e:
                        print(f"Warning: Could not remove {temp_file}: {str(e)}")

    def update_company_tickers(self):
        """Update company tickers data files."""
        return asyncio.run(self._update_company_tickers())

    def update_company_metadata(self):
        """Update company metadata and former names files."""
        return asyncio.run(self._update_company_metadata())