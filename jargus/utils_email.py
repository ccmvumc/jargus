import os
from datetime import datetime
from email.message import EmailMessage
import smtplib

from .oldsecrets import EMAIL_PASS, EMAIL_USER


def send_email(html_content, email_to, email_subject, pdf=None):
    if isinstance(email_to, str):
        email_to = [email_to]

    email_host = "smtp.gmail.com"
    email_port = 465
    email_username = EMAIL_USER
    email_password = EMAIL_PASS

    msg = EmailMessage()
    msg['From'] = email_username
    msg['Subject'] = f'{email_subject}'
    msg['To'] = email_to
    msg.set_content('html')
    msg.add_alternative(html_content, subtype='html')

    if pdf:
        with open(pdf, 'rb') as f:
            content = f.read()
            msg.add_attachment(
                content,
                maintype='application',
                subtype='pdf',
                filename=os.path.basename(pdf))

    with smtplib.SMTP_SSL(email_host, email_port) as smtp:
        smtp.login(email_username, email_password)
        smtp.send_message(msg, to_addrs=email_to + ['brian.d.boyd@vumc.org'])
