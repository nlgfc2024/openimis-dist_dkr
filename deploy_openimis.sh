#!/bin/bash
#rename .env
if [[ -f '.env' ]]
then
echo "Using existing env files"
else
echo "creating env files from example"
cp .env.example .env
cp .env.lightning.example .env.lightning
cp .env.openSearch.example .env.openSearch
fi


if [[ -f '.init.lock' ]]
then
echo "initialisation already done"
else
echo "initialisation"

docker compose  up -d db
#wait for the db to be initialised
sleep 180
#load the .env file in your shell to have the access to the env variables
source .env
source .env.lightning
# create the lightning database
docker compose  run -e  PGPASSWORD=${POSTGRES_PASSWORD} --rm db createdb -h db -U ${POSTGRES_USER}  ${POSTGRES_DB}
set -e
# init lighning
docker compose  run --rm  web mix ecto.migrate
docker compose  run --rm web mix run imisSetupScripts/imisSetup.exs
#TODO init opensearch dashboard with API/ manage command
echo "connect to https://{DOMAIN}"
echo "then go to https://{DOMAIN}/opensearch"
echo "then go in manage / saved object / import to import the openSearch dashboard"
touch '.init.lock' 
fi
docker compose up -d
#load opensearch dashbooard
docker compose  exec --rm -e MODE=DEV backend manage upload_opensearch_dashboards --host-domain https://demo.openimis.org --imis-password admin123 



