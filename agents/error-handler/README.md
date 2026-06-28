# Error Handler

Catches errors from any workflow and sends a WhatsApp alert to the admin instantly.

## What it Does

When any n8n workflow throws an error this handler:
1. Catches it via n8n Error Trigger
2. Formats an alert with workflow name, node name and error details
3. Sends it as a WhatsApp message to your admin number

## How to Set Up

1. Import workflow.json into n8n
2. In the CONFIG node update:
   - phoneNumberId with your WhatsApp Business phone number ID from Meta Developer Console
   - adminPhone with your WhatsApp number in international format without + sign
3. In the WA Alert Admin node add your Meta WA Token credential
4. In each of your other workflows go to Settings > Error Workflow and select this workflow
5. Activate this workflow

## Required Credentials

Meta WA Token from Meta Developer Console
