# import necessary packages
 
import os
import sys
import time
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.utils import formatdate
import config

 # create message object instance
msg = MIMEMultipart()
 
date = sys.argv[2]
id = sys.argv[3]
 
message = "A motion event has ocurred at date: "+date+", more details at: "+config.HOST+config.PORT+"/event-details?id="+id
 
# setup the parameters of the message
msg['From'] = config.MAIL_FROM
password = config.MAIL_FROM_PASSWORD
msg['To'] = config.MAIL_TO
msg['Subject'] = "Pisegur alarm"
msg["Date"] = formatdate(localtime=True)
 
# add in the message body
msg.attach(MIMEText(message, 'plain'))

# attach image
date_splited = date.split(' ')
day = date_splited[0]
hours = date_splited[1]

filename = 'static/events/'+day+'/'+hours+'.jpg'
print (filename)
img_data = open(filename, 'rb').read()
image = MIMEImage(img_data, name=os.path.basename(filename))
msg.attach(image)
 
#create server
server = smtplib.SMTP(config.SMTP_SERVER+': '+config.SMTP_SERVER_PORT)
 
server.starttls()
 
# Login Credentials for sending the mail
server.login(msg['From'], password)
  
# send the message via the server.
server.sendmail(msg['From'], msg['To'], msg.as_string())
 
server.quit()
 
print "successfully sent email to %s:" % (msg['To'])
