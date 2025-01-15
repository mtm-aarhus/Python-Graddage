"""This module contains the main process of the robot."""

from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection
from OpenOrchestrator.database.queues import QueueElement
import paramiko     # SFTP Konto
import requests     # API Requests
from datetime import datetime, timedelta
import locale       # Timestamp | Lokaltid
import os

# pylint: disable-next=unused-argument
def process(orchestrator_connection: OrchestratorConnection, queue_element: QueueElement | None = None) -> None:
    """Do the primary process of the robot."""
    orchestrator_connection.log_trace("Running process.")
    # Set the locale to Danish
    locale.setlocale(locale.LC_TIME, 'da_DK.UTF-8')
    
    # Calculate dates
    today = datetime.now()
    from_date = today - timedelta(days=30)
    to_date = today - timedelta(days=1)

    # Get Danish month names
    from_date_str = from_date.strftime('%Y-%m-%d')
    to_date_str = to_date.strftime('%Y-%m-%d')

    # Construct the API URL
    dmi = orchestrator_connection.get_credential("DMI Api-nøgle")
    api_key = dmi.password
    municipality_id = "0751"
    parameter_id = "mean_temp"
    time_resolution = "day"

    api_url = (
        f"{dmi.username}/v2/climateData/collections/municipalityValue/items"
        f"?api-key={api_key}"
        f"&municipalityId={municipality_id}"
        f"&parameterId={parameter_id}"
        f"&timeResolution={time_resolution}"
        f"&datetime={from_date_str}T00:00:00.000Z/{to_date_str}T00:00:00.000Z"
    )

    # Fetch data from API

    response = requests.get(api_url)
    response.raise_for_status()  # Raise an error for bad status codes
    data = response.json()       # Parse the JSON response
    # Extract features
    features = data.get('features', [])
    results = []
    
    for feature in features:
        props = feature.get('properties', {})
        mean_temp = props.get('value', None)
        
        if mean_temp is not None:
            if mean_temp < 17:
                adjusted_value = 17 - mean_temp
            else:
                adjusted_value = 0
            
            # Convert adjustment to use comma as decimal separator
            adjusted_value = str(adjusted_value).replace('.', ',')

            # Extract year, month and day from 'from' field
            from_date_raw = props.get('from', '')
            from_year = from_date_raw[:4]   # Extract year (yyyy)
            from_month = from_date_raw[5:7] # Extract month (MM)
            from_day = from_date_raw[8:10]  # Extract day (DD)
            
            results.append({
                'Station' : "607400",       # Vejrstation | Aarhus | Stationær værdi
                'from_year': from_year,     # År
                'from_month': from_month,   # Måned
                'from_day' : from_day,      # Dag
                '147': adjusted_value       # Graddage
            })
    
    # Print results
    for result in results:
        orchestrator_connection.log_info(result)

    # Write results to a CSV file
    csv_file = today.strftime('%Y-%m-%d_%H%M%S') + "_Graddage.csv"
    with open(csv_file, mode='w', encoding='utf-8') as file:
        file.write("Station;year;month;day;147\n")
        for result in results:
            file.write(f"{result['Station']};{result['from_year']};{result['from_month']};{result['from_day']};{result['147']}\n")
    
    orchestrator_connection.log_info(f"Data written to {csv_file}")

    # Upload the CSV file to an SFTP server
    server = orchestrator_connection.get_credential("CrushFTPPortServer")
    credentials = orchestrator_connection.get_credential("ChrushFTPGraddage")
    sftp_server = server.password
    sftp_port = server.username
    sftp_user = credentials.username
    sftp_password = credentials.password
    
    # Set up the SFTP connection
    transport = paramiko.Transport((sftp_server, sftp_port))
    transport.connect(username=sftp_user, password=sftp_password)
    
    with paramiko.SFTPClient.from_transport(transport) as sftp:
        remote_path = f"GraddagePython/{csv_file}"                  # Specify the remote directory
        sftp.put(csv_file, remote_path)                             # Upload the file to the 'GraddagePython' folder
    
    transport.close()
    orchestrator_connection.log_info(f"File {csv_file} uploaded to SFTP server {sftp_server} in 'GraddagePython' folder")

    os.remove(csv_file)
