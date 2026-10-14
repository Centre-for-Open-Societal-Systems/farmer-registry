#!/usr/bin/env python3
"""
Test script for verifying ODK Central -> OpenG2P Connector Service end-to-end pipeline.
Submits an XML survey instance to the deployed ODK Central server, then monitors
the OpenG2P Connector Service until the submission is fetched, transformed, and
enqueued into the Intake Forms queue.
"""

import sys
import time
import uuid
import json
import ssl
import urllib.request
import urllib.parse
from datetime import datetime, timezone

# Server & Connector Configuration
ODK_BASE_URL = "https://odk.13.207.43.8.nip.io"
ODK_PROJECT_ID = 13
ODK_FORM_ID = "farmer_profile"
ODK_APP_USER_TOKEN = "CBgWA1NO$BWgO5vTjqPajzi2TlAmHUOeAf6CH9IYygRP$BvyotGIVlVA8bIHgseT"  # Field_Officer_1

CONNECTOR_API_URL = "http://localhost:8050"
CONNECTOR_ID = "farmer-odk-pipeline-01"

# Disable SSL verification for self-signed certificates on test/sandbox
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def submit_to_odk_central(farmer_name="TestFarmer", father_name="ManualCheck"):
    instance_id = f"uuid:{uuid.uuid4()}"
    now_iso = datetime.now(timezone.utc).isoformat()
    random_id = uuid.uuid4().hex[:6].upper()

    xml_payload = f"""<?xml version="1.0" encoding="UTF-8" ?>
<data id="{ODK_FORM_ID}" version="1.0.2" xmlns:h="http://www.w3.org/1999/xhtml" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:jr="http://openrosa.org/javarosa" xmlns:ev="http://www.w3.org/2001/xml-events" xmlns:orx="http://openrosa.org/xforms" xmlns:odk="http://www.opendatakit.org/xforms">
  <consent_form_section><consent_form>agree</consent_form></consent_form_section>
  <household_questions><household_head>yes</household_head><head_registered>no</head_registered></household_questions>
  <national_id_section><national_id>yes</national_id><national_uid>9876 5432 1098 {random_id[:4]}</national_uid><national_uid_confirm>9876 5432 1098 {random_id[:4]}</national_uid_confirm></national_id_section>
  <basic_info>
    <locale_info><region>2</region><zone>206</zone><woreda>20601</woreda><kebele>20601101001</kebele><language>Amharic</language></locale_info>
    <personal_info>
      <first_name_english>{farmer_name}</first_name_english>
      <father_name_english>{father_name}</father_name_english>
      <grandfather_name_english>AutoTest</grandfather_name_english>
      <first_name_amharic>ሙከራ</first_name_amharic>
      <father_name_amharic>አለሙ</father_name_amharic>
      <grandfather_name_amharic>በቀለ</grandfather_name_amharic>
      <gender>male</gender>
      <date_of_birth>1985-05-15</date_of_birth>
      <calculated_age>41</calculated_age>
      <age>41</age>
      <phone_number>yes</phone_number>
      <primary_phone_number>251911{random_id[:6]}</primary_phone_number>
      <farming_type>mixed_farming</farming_type>
      <disability>no</disability>
    </personal_info>
  </basic_info>
  <socio_economic_data><marital_status>married</marital_status><education_level>secondary</education_level><income_source>crop</income_source></socio_economic_data>
  <membership><primary_cooperative>no</primary_cooperative><coop_union>no</coop_union><farmer_cluster>no</farmer_cluster></membership>
  <land_info>
    <land_info_repeat><land_ownership>owner</land_ownership><total_land_area>2.8</total_land_area><land_id>LND-{random_id}</land_id></land_info_repeat>
  </land_info>
  <crop_information>
    <crop_repeat><crop_name>wheat</crop_name><crop_date>2026-09-25</crop_date></crop_repeat>
    <crop_water_source>rainfall</crop_water_source>
  </crop_information>
  <agricultural_input><fertilizer_utilized>yes</fertilizer_utilized><pesticide_utilized>no</pesticide_utilized><insecticide_utilized>no</insecticide_utilized><improved_seed_utilized>yes</improved_seed_utilized></agricultural_input>
  <access_to_resource><machinery_access>no</machinery_access></access_to_resource>
  <access_to_finance><finance_access>no</finance_access></access_to_finance>
  <farmer_reference_id_section>
    <fl_first_name>T</fl_first_name><fl_father_name>M</fl_father_name><fl_grandfather_name>A</fl_grandfather_name>
    <random_part1>1234</random_part1><random_part2>5678</random_part2><random_part3>{now_iso[:10]}</random_part3>
    <farmer_reference_id>TMA-1234-5678-{random_id}</farmer_reference_id>
  </farmer_reference_id_section>
  <farmer_location><location>9.0123 38.7456 2300 5.0</location></farmer_location>
  <submission_time>{now_iso}</submission_time>
  <meta><instanceID>{instance_id}</instanceID></meta>
</data>
"""

    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="xml_submission_file"; filename="submission.xml"\r\n'
        f"Content-Type: text/xml\r\n\r\n"
        f"{xml_payload}\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")

    submission_url = f"{ODK_BASE_URL}/v1/key/{urllib.parse.quote(ODK_APP_USER_TOKEN)}/projects/{ODK_PROJECT_ID}/submission"

    req = urllib.request.Request(
        submission_url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-OpenRosa-Version": "1.0",
        }
    )

    print(f"[*] Submitting test record to ODK Central: {submission_url}")
    print(f"[*] Farmer Name: {farmer_name} {father_name}")
    print(f"[*] Instance ID: {instance_id}")

    with urllib.request.urlopen(req, context=ctx) as resp:
        if resp.status in (200, 201, 202):
            print(f"[+] ODK Central accepted submission! HTTP {resp.status}")
            return instance_id
        else:
            print(f"[-] Unexpected response from ODK Central: HTTP {resp.status}")
            return None

def trigger_connector_poll():
    poll_url = f"{CONNECTOR_API_URL}/connectors/{CONNECTOR_ID}/poll"
    req = urllib.request.Request(poll_url, data=b"{}", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            print(f"[+] Triggered immediate poll on connector: task_id={data.get('task_id')}")
            return True
    except Exception as e:
        print(f"[-] Could not trigger poll API: {e} (it will poll automatically every 30s)")
        return False

def check_connector_status():
    url = f"{CONNECTOR_API_URL}/connectors/{CONNECTOR_ID}"
    try:
        with urllib.request.urlopen(url) as resp:
            data = json.loads(resp.read().decode())
            print(f"[*] Connector last poll status: {data.get('last_poll_status')}")
            print(f"[*] Connector last poll at:     {data.get('last_poll_at')}")
            return data
    except Exception as e:
        print(f"[-] Error querying connector: {e}")
        return None

def main():
    print("=" * 65)
    print("   ODK Central -> OpenG2P Connector End-to-End Test")
    print("=" * 65)

    name = input("\nEnter test farmer first name (default 'ManualTest'): ").strip() or "ManualTest"
    father = input("Enter test farmer father name (default 'DevOpsCheck'): ").strip() or "DevOpsCheck"

    try:
        inst_id = submit_to_odk_central(name, father)
        if not inst_id:
            print("[-] Submission failed.")
            return

        print("\n[*] Triggering Connector Service poll...")
        trigger_connector_poll()

        print("[*] Waiting 5 seconds for Celery worker & Partner API ingestion...")
        time.sleep(5)
        check_connector_status()

        print("\n" + "=" * 65)
        print("VERIFICATION CHECKLIST:")
        print("1. Connector UI:")
        print(f"   Open: http://localhost:5173")
        print("   Check 'Runs' tab for successful ingestion run.")
        print("\n2. Staff Portal Intake Forms Queue:")
        print("   Open: http://localhost:3001/en/intake-form/farmer")
        print(f"   Look for pending farmer application for '{name} {father}'.")
        print("=" * 65)

    except Exception as e:
        print(f"[-] Test failed with error: {e}")

if __name__ == "__main__":
    main()
