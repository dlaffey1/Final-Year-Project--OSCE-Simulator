
### python pre-commit hook:
pre-commit run pytest --all-files


### Testing on Postman:
Download the "NSSPI Endpoints.postman_collection.json" file and import it into Postman

Make sure the Django project is running locally

The endpoints can then be run in Postman

### Activate virtual environment + install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
