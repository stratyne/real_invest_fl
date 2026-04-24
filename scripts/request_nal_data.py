"""
Generates the email body for the Florida DOR NAL + SDF data request.
Prints to stdout — copy and send to PTOTechnology@floridarevenue.com
Usage: python scripts/request_nal_data.py
"""

EMAIL_BODY = """
Subject: Public Records Request — NAL and SDF Data Files, Escambia County (CO_NO 28)

To: PTOTechnology@floridarevenue.com

Good morning,

I am writing to request access to the following public records pursuant to
Florida Statutes Chapter 119 and Section 193.085:

  1. The current Name-Address-Legal (NAL) file for Escambia County (County Number 28),
     in the standard comma-delimited CSV format as defined in the 2025 NAL Summary
     Table of Data Fields.

  2. The current Sale Data File (SDF) for Escambia County (County Number 28),
     in the standard comma-delimited CSV format.

These files will be used for lawful private investment research purposes.
No confidential fields (SSN, exempt owner addresses per s. 119.071) are requested
or required.

Please advise on file size so I may confirm the appropriate delivery method
(email for files under 10 MB, or a temporary download link for larger files).

Thank you for your assistance.

[YOUR NAME]
[YOUR PHONE]
[YOUR EMAIL]
"""

if __name__ == "__main__":
    print(EMAIL_BODY)
