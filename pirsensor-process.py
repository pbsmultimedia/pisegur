import time
import sys
from picamera import PiCamera
import RPi.GPIO as GPIO
import os
import subprocess
import requests

# set BCM_GPIO 17(GPIO 0) as PIR pin
PIRPin = 17 

# BCM numbering
GPIO.setmode(GPIO.BCM)

GPIO.setup(PIRPin,GPIO.IN)

def loop():
	print('PIR process function called via argv')
	while True:

		motion_detected = 0

		# stuff for folder and file names    
		hours = time.strftime("%H:%M:%S") # use another format for hours..?	
		hours_simple = hours.replace(':','_')
		day = time.strftime("%Y-%m-%d")

		date = time.strftime("%Y-%m-%d %H:%M:%S")

		# motion detected on PIR sensor
		if(GPIO.input(PIRPin) != 0 and motion_detected == 0):
			
			print ("ALARM\nmotion detected - "+date)
			
			motion_detected = 1
			
			# kill security camera video stream (maybe running and will cause error)
			x = subprocess.Popen(['sudo','pkill','uv4l'])
			print "uv4l process pkill result: "+str(x)
									
			# start and config camera
			camera = PiCamera()
			camera.hflip = True
			camera.vflip = True
			
			# create folder to store picture and video
			if not os.path.exists('static/events/'+day):
				os.makedirs('static/events/'+day)
			
			# send mail, create entry on database..
			# TO-DO: store the files on the cloud..?
			# could just extract a frame of the video, instead of taking a pic?
			p = camera.capture('static/events/'+day+'/'+hours+'.jpg')
			print('picture taken')
			
			# record video
			camera.start_recording('static/events/'+day+'/'+hours_simple+'.h264')
			time.sleep(10)
			# record for 5 seconds then stop
			camera.stop_recording()
			print ("storing video..")
			camera.close()
			del camera
			
			# convert h264 to mp4
			time.sleep(2) # wait for video to be stored..
			print ('converting video')
			os.system("MP4Box -add static/events/"+day+"/"+hours_simple+".h264 static/events/"+day+"/"+hours_simple+".mp4")
			
			print ('video stored')

			# notify the core of the app via POST, after the picture is ready
			# TO-DO: some kind of validation..
			requests.post(url='http://127.0.0.1:5000/alert', data={'event':'motion', 'date': date})
		
			motion_detected = 0
		
		# time between each motion verification
		time.sleep(.5)

# function is called via CLI                
fn = eval(sys.argv[2])
fn()
