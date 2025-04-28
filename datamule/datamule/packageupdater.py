import asyncio
import aiohttp
import json
import csv
import os
import logging
from pkg_resources import resource_filename
from tqdm import tqdm
from .helper import headers
from pprint import pformat
from .downloader.downloader import PreciseRateLimiter, RateMonitor

# Set up logging based on environment variable
log_level = os.getenv("DATAMULE_LOG_LEVEL", "WARNING").upper()


class TqdmLoggingHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            tqdm.write(msg)
            self.flush()
        except Exception:
            self.handleError(record)


logging.basicConfig(
    level=getattr(logging, log_level, logging.WARNING),
    format="%(message)s",
    handlers=[TqdmLoggingHandler()],
)
logger = logging.getLogger(__name__)


class PackageUpdater:
    def __init__(self):
        self.limiter = PreciseRateLimiter(5)  # 5 requests per second
        self.rate_monitor = RateMonitor()
        self.headers = headers
        self.timeout = aiohttp.ClientTimeout(total=30)  # 30 second timeout
        self.max_retries = 3
        # Get the directory where this file is located
        self.package_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.path.join(self.package_dir, "data")

    async def _fetch_json(self, session, url, retry_count=0):
        logger.debug(f"Fetching {url}")
        """Fetch JSON with rate limiting and monitoring."""
        async with self.limiter:
            try:
                logger.debug(f"Fetching {url}")
                async with session.get(url, timeout=self.timeout) as response:
                    response.raise_for_status()
                    logger.debug(f"Reading content from {url}")
                    content = await response.read()
                    logger.debug(f"Content length: {len(content)}")
                    await self.rate_monitor.add_request(len(content))
                    logger.debug(f"Parsing JSON from {url}")
                    response_json = await response.json()
                    logger.debug(f"Response content:\n{pformat(response_json)}")
                    return response_json
            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                if retry_count < self.max_retries:
                    logger.warning(
                        f"Retry {retry_count + 1} for {url} after error: {str(e)}"
                    )
                    await asyncio.sleep(1 * (retry_count + 1))  # Exponential backoff
                    return await self._fetch_json(session, url, retry_count + 1)
                logger.error(
                    f"Failed after {self.max_retries} retries for {url}: {str(e)}"
                )
                return None
            except Exception as e:
                logger.error(f"Error fetching {url}: {str(e)}")
                return None

    async def _update_company_tickers(self):
        """Update company tickers data files."""
        url = "https://www.sec.gov/files/company_tickers.json"

        # Define file paths using the package's data directory
        json_file = os.path.join(self.data_dir, "company_tickers.json")
        csv_file = os.path.join(self.data_dir, "company_tickers.csv")

        # Define temporary file paths
        temp_json_file = json_file + ".temp"
        temp_csv_file = csv_file + ".temp"

        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                data = await self._fetch_json(session, url)
                if not data:
                    raise Exception("Failed to fetch company tickers data")

                # Save the raw JSON file
                with open(temp_json_file, "w") as f:
                    json.dump(data, f, indent=4)

                # Convert to CSV
                with open(temp_csv_file, "w", newline="") as csvfile:
                    fieldnames = ["cik", "ticker", "title"]
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    for _, company in data.items():
                        writer.writerow(
                            {
                                "cik": str(company["cik_str"]).zfill(10),
                                "ticker": company["ticker"],
                                "title": company["title"],
                            }
                        )

                # Replace original files
                for src, dst in [
                    (temp_json_file, json_file),
                    (temp_csv_file, csv_file),
                ]:
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

    async def _process_metadata_batch(
        self, session, companies, metadata_writer, former_names_writer
    ):
        """Process a batch of companies for metadata updates."""
        metadata_fields = [
            "cik",
            "name",
            "entityType",
            "sic",
            "sicDescription",
            "ownerOrg",
            "insiderTransactionForOwnerExists",
            "insiderTransactionForIssuerExists",
            "tickers",
            "exchanges",
            "ein",
            "description",
            "website",
            "investorWebsite",
            "category",
            "fiscalYearEnd",
            "stateOfIncorporation",
            "stateOfIncorporationDescription",
            "phone",
            "flags",
            "mailing_street1",
            "mailing_street2",
            "mailing_city",
            "mailing_stateOrCountry",
            "mailing_zipCode",
            "mailing_stateOrCountryDescription",
            "mailing_isForeignLocation",
            "mailing_countryCode",
            "mailing_foreignStateTerritory",
            "mailing_country",
            "business_street1",
            "business_street2",
            "business_city",
            "business_stateOrCountry",
            "business_zipCode",
            "business_stateOrCountryDescription",
            "business_isForeignLocation",
            "business_countryCode",
            "business_foreignStateTerritory",
            "business_country",
        ]

        logger.debug(
            f"\nProcessing batch with CIKs: {[company['cik'] for company in companies]}"
        )
        tasks = []
        for company in companies:
            cik = company["cik"]
            url = f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json"
            tasks.append(self._fetch_json(session, url))

        try:
            logger.debug("Waiting for batch requests to complete...")
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=120,  # 2 minute timeout for entire batch
            )
            logger.debug("Batch requests completed")
        except asyncio.TimeoutError:
            logger.warning("Batch timeout occurred, processing partial results")
            results = [None] * len(tasks)
        except Exception as e:
            logger.error(f"Error in gather: {str(e)}")
            return

        logger.debug("Processing batch results...")
        for company, result in zip(companies, results):
            if isinstance(result, Exception) or not result:
                logger.warning(
                    f"Error processing CIK {company['cik']}: {str(result) if isinstance(result, Exception) else 'No data'}"
                )
                empty_row = {field: "" for field in metadata_fields}
                empty_row["cik"] = company["cik"]
                metadata_writer.writerow(empty_row)
                continue

            try:
                logger.debug(f"Processing metadata for CIK {company['cik']}")
                logger.debug(f"Result:\n{pformat(result)}")
                metadata = {
                    field: result.get(field, "")
                    for field in metadata_fields
                    if field not in ["tickers", "exchanges"]
                }
                metadata["cik"] = company["cik"]
                metadata["tickers"] = ",".join(result.get("tickers", []) or [])
                metadata["exchanges"] = ",".join(
                    [x for x in (result.get("exchanges", []) or []) if x is not None]
                )

                # Add address information
                for address_type in ["mailing", "business"]:
                    address = result.get("addresses", {}).get(address_type, {})
                    for key, value in address.items():
                        metadata[f"{address_type}_{key}"] = (
                            value if value is not None else ""
                        )

                metadata_writer.writerow(metadata)

                for former_name in result.get("formerNames", []):
                    if former_name.get("name"):  # Only process if name exists
                        former_names_writer.writerow(
                            {
                                "cik": company["cik"],
                                "former_name": former_name["name"],
                                "from_date": former_name.get("from", ""),
                                "to_date": former_name.get("to", ""),
                            }
                        )
                logger.debug(f"Completed processing CIK {company['cik']}")

            except Exception as e:
                logger.error(
                    f"Error processing metadata for CIK {company['cik']}: {str(e)}"
                )
                empty_row = {field: "" for field in metadata_fields}
                empty_row["cik"] = company["cik"]
                metadata_writer.writerow(empty_row)

    async def _update_company_metadata(
        self, batch_size: int = 10, cik_list: list[str] = None, output_file: str = None
    ):
        """Update company metadata and former names files."""
        metadata_file = (
            output_file
            if output_file
            else os.path.join(self.data_dir, "company_metadata.csv")
        )
        former_names_file = os.path.join(self.data_dir, "company_former_names.csv")

        temp_metadata_file = metadata_file + ".temp"
        temp_former_names_file = former_names_file + ".temp"

        # Load current company tickers
        with open(os.path.join(self.data_dir, "company_tickers.csv"), "r") as f:
            company_tickers = list(csv.DictReader(f))

        metadata_fields = [
            "cik",
            "name",
            "entityType",
            "sic",
            "sicDescription",
            "ownerOrg",
            "insiderTransactionForOwnerExists",
            "insiderTransactionForIssuerExists",
            "tickers",
            "exchanges",
            "ein",
            "description",
            "website",
            "investorWebsite",
            "category",
            "fiscalYearEnd",
            "stateOfIncorporation",
            "stateOfIncorporationDescription",
            "phone",
            "flags",
            "mailing_street1",
            "mailing_street2",
            "mailing_city",
            "mailing_stateOrCountry",
            "mailing_zipCode",
            "mailing_stateOrCountryDescription",
            "mailing_isForeignLocation",
            "mailing_countryCode",
            "mailing_foreignStateTerritory",
            "mailing_country",
            "business_street1",
            "business_street2",
            "business_city",
            "business_stateOrCountry",
            "business_zipCode",
            "business_stateOrCountryDescription",
            "business_isForeignLocation",
            "business_countryCode",
            "business_foreignStateTerritory",
            "business_country",
        ]

        former_names_fields = ["cik", "former_name", "from_date", "to_date"]

        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                with open(temp_metadata_file, "w", newline="") as mf, open(
                    temp_former_names_file, "w", newline=""
                ) as fnf:

                    metadata_writer = csv.DictWriter(mf, fieldnames=metadata_fields)
                    metadata_writer.writeheader()

                    former_names_writer = csv.DictWriter(
                        fnf, fieldnames=former_names_fields
                    )
                    former_names_writer.writeheader()

                    if cik_list:
                        companies = [
                            company
                            for company in company_tickers
                            if str(company["cik"]).zfill(10) in cik_list
                        ]
                    else:
                        companies = company_tickers

                    # Process in batches of 10 companies with progress bar
                    total_companies = len(companies)
                    progress_bar = tqdm(total=total_companies, desc="Processing CIKs")

                    for i in range(0, total_companies, batch_size):
                        batch = companies[i : i + batch_size]
                        await self._process_metadata_batch(
                            session, batch, metadata_writer, former_names_writer
                        )
                        progress_bar.update(len(batch))

                    progress_bar.close()

            # Replace original files
            for src, dst in [
                (temp_metadata_file, metadata_file),
                (temp_former_names_file, former_names_file),
            ]:
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

    def update_company_metadata(self, batch_size=10, cik_list=None, output_file=None):
        """Update company metadata and former names files."""
        return asyncio.run(
            self._update_company_metadata(batch_size, cik_list, output_file)
        )
