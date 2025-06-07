The following secrets are available

AZURE_SUBSCRIPTION_ID
AZURE_CLIENT_SECRET
AZURE_TENANT_ID
AZURE_CLIENT_ID

You can gain the use of az cli with the following preamble

az login --service-principal \
  --username "$AZURE_CLIENT_ID" \
  --password "$AZURE_CLIENT_SECRET" \
  --tenant "$AZURE_TENANT_ID"

az account set --subscription "$AZURE_SUBSCRIPTION_ID"

If you need az, you will first need to install the cli using:

curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

## Firecrawl utilities

Two helper scripts are available in the project root:

* **web_search.py** – search the web using Firecrawl. Usage:
  `./web_search.py <query>`
* **get_url.py** – scrape a URL and output markdown. Usage:
  `./get_url.py <url>`

Both scripts require the `firecrawl-py` package which is listed in `requirements-worker.txt`.
