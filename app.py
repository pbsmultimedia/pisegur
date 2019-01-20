#!/usr/bin/env python

# convert h264 to mp4
# sudo apt-get install -y gpac

from flask import Flask, render_template, Response, request, redirect, session
from dht11 import read_dht11_dat
import time
import subprocess
import os, signal
from urlparse import urlparse
# sudo pip install Flask-SQLAlchemy
from flask_sqlalchemy import SQLAlchemy
import requests
from urlparse import parse_qs, urlparse
import config
from threading import Thread

armed = ''

pirSensorProcessId = ''

streaming = 0

app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///pisegur.db"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

app.secret_key = config.SECRET_KEY

@app.before_first_request
def init_app():
	# ... do some preparation here ...
	session.permanent = True
	global armed
	global pirSensorProcessId
	# get status from DB
	s = db.session.query(SystemStatus).filter(SystemStatus.status == "armed").first()
	if(s):
		print ('DB status is armed with id:'+str(s.id))
		session['armed'] = 1
		armed = 1
		pirsensor()
		# store new pir process id
		s.pir_sensor_process_id = pirSensorProcessId
		db.session.commit()
	else:
		print ('DB status is disarmed')
		session['armed'] = 0
		armed = 0

	# run record temperature on another thread
	Thread(target=record_temperature).start()

@app.route('/')
def index():
	result = get_temperature()
	humidity, temperature = result

	e = db.session.query(Event).filter(Event.seen == None).count()

	global armed

	data = {
		'pirSensorProcessId': pirSensorProcessId,
		'temperature': temperature,
		'humidity': humidity,
		'events_unseen': e,
		'armed': armed
		}

	# if streaming video, stop
	global streaming

	if(streaming == 1):
		mjpeg_stop()
		
	return render_template('index.html', data=data)


@app.route('/status')
def status():
    return "armed: "+str(armed)+" pirsensor process id: "+str(pirSensorProcessId)


@app.route('/arm')
def arm():
    global armed
    global pirSensorProcessId
    armed = 1
    pirsensor()    
    session['armed'] = armed
    # store status on DB, if app or server reboots, set previous state
    s = SystemStatus(date_start=time.strftime("%Y-%m-%d %H:%M:%S"), status="armed", pir_sensor_process_id=pirSensorProcessId)
    db.session.add(s)
    db.session.commit()
    print("system armed, status recorded")
    return redirect('/', code=302)


@app.route('/disarm')
def disarm():
	global armed
	armed = 0
	session['armed'] = armed
	s = db.session.query(SystemStatus).filter(SystemStatus.status == "armed").first()    
	if(s):
		s.status = "disarmed"
		s.date_end = time.strftime("%Y-%m-%d %H:%M:%S")
		db.session.commit()    
		stop_pir_sensor_process()
		print("system disarmed, db id: "+str(s.id))
	return redirect('/', code=302)


@app.route('/pirsensor')
def pirsensor():    
    global pirSensorProcessId
    process = subprocess.Popen(["python", "pirsensor-process.py", "-c", "loop"])
    pirSensorProcessId = process.pid    
    print(" > Process id {}".format(pirSensorProcessId))    
    return 'process started with id: '+str(pirSensorProcessId)


@app.route('/temperature')
def get_temperature():
    
    result = read_dht11_dat()
    
    if (result):                
        return result
    else:        
        time.sleep(1)
        return get_temperature() # recursive


@app.route('/record-temperature')
def record_temperature():
    result = read_dht11_dat()
    if (result):
        humidity, temperature = result
        t = Temperature(date=time.strftime("%Y-%m-%d %H:%M:%S"), temperature=temperature, humidity=humidity)
        db.session.add(t)
        db.session.commit()        
        print 'temperature recorded'
        time.sleep(3600)
        record_temperature()
    else:        
        time.sleep(1)
        return record_temperature() # recursive

@app.route('/list-temperatures')
def list_temperatures():
	r = db.engine.execute("SELECT MIN(temperature) AS min, MAX(temperature) AS max, MAX(humidity) AS humidity_max, MIN(HUMIDITY) AS humidity_min, substr(date,1,10) AS date FROM temperature GROUP BY substr(date,1,10)")	
	l = []
	min = []
	max = []
	humidity_min = []
	humidity_max = []
	for x in r:
		l.append(x.date)
		min.append(x.min)
		max.append(x.max)
		humidity_min.append(x.humidity_min)
		humidity_max.append(x.humidity_max)
	t = Temperature.query.order_by(Temperature.id.desc()).all()	
	return render_template('list-temperatures.html', t=t, l=l, min=min, max=max, humidity_min=humidity_min, humidity_max=humidity_max)
	
@app.route('/list-events')
def list_events():	
	
	url = request.url	
	parsed_url = urlparse(url)

	e = Event.query.order_by(Event.id.desc()).all()
	return render_template('list-events.html', e=e)
	
	
@app.route('/event-details')
def event_details():
	
	url = request.url	
	parsed_url = urlparse(url)
	
	id = parse_qs(parsed_url.query)['id'][0]
	
	try:
		parse_qs(parsed_url.query)['delete'][0]		
		delete_event(id)
		# url_for not working with redirect..?
		return redirect('/list-events', code=302)		
	except:
		pass	
			
	e = db.session.query(Event).filter(Event.id == id).first()	
	
	# mark event as seen
	if( e.seen is None ):
		e.seen = 1;
		db.session.commit()	
	
	date_splited = e.date.split(' ');
	day = date_splited[0]
	hours = date_splited[1]
	# problems with : on the filename
	hours_simple = hours.replace(':','_')
	
	folder = 'static/'+day
	picture = folder+'/'+hours+'.jpg'	
	video = folder+'/'+hours_simple	
	
	return render_template('event-details.html', e=e)


def delete_event(id):
			
	e = db.session.query(Event).filter(Event.id == id).first()
	
	# delete picture and video from disk
	date_splited = e.date.split(' ');
	day = date_splited[0]
	hours = date_splited[1]
	
	folder = 'static/'+day
	picture = folder+'/'+hours+'.jpg'
	video = folder+'/'+hours+'.h264'
	
	# check if picture exists
	if( os.path.exists(picture)):
				
		try:
			os.remove(picture)
		except OSError as e: # name the Exception `e`
			print "Failed with:", e.strerror # look what it says
			print "Error code:", e.code 
	else:
		print ('picture does not exist: '+picture)
	
	# check if video exists
	if( os.path.exists(video)):
		#os.remove(picture)
		#print ('deleted file: '+picture)
		try:
			os.remove(video)
		except OSError as e: # name the Exception `e`
			print "Failed with:", e.strerror # look what it says
			print "Error code:", e.code 
	else:
		print ('video does not exist: '+video)

	db.session.delete(e)
	db.session.commit()
	
	return 1

@app.route('/mjpeg')
def mjpeg():
    
    global streaming
    
    if(streaming == 0):
        streaming = 1
        os.system("uv4l --auto-video_nr --driver raspicam --encoding mjpeg --vflip --hflip --server-option '--port=9000'")
        
    return render_template('video.html', url=urlparse(request.base_url).hostname+':9000/stream/video.mjpeg')

@app.route('/mjpeg-stop')
def mjpeg_stop():
    global streaming
    
    if(streaming == 1):
        streaming = 0
        subprocess.Popen(['sudo','pkill','uv4l'])
        print "uv4l process stopped"
    else:
        print "uv4l process not running"
    
    return redirect('/', code=302)


def stop_pir_sensor_process():
	global pirSensorProcessId
	print ('pirSensorProcessId: '+str(pirSensorProcessId))
	if(pirSensorProcessId != ''):
		print ('killing pirSensorProcessId: '+str(pirSensorProcessId))
		os.kill(pirSensorProcessId, signal.SIGTERM)
		pirSensorProcessId = ''
		process = None
		return 'pirsensor process killed'
	else:
		return 'pirsensor process not running'


@app.route('/alert', methods=['POST'])
def alert():    
    
    print('event received: '+request.form['event'])
    
    if(request.form['event'] == 'motion'):
        
        # video streaming was killed at pirsensor subprocess
        global streaming
        streaming = 0        
        
        # store event on DB
        # use always the same date - the one of the PIR motion event
        date = request.form['date']
        print('received event date at app.py is: '+date)
        e = Event(date = date, type = 'motion')
        db.session.add(e)
        db.session.commit()
        print ("id of stored event: "+str(e.id))
        
        # send e-mail and SMS
        print ("calling e-mail process")
        subprocess.Popen(["python", "email-process.py", "-c", date, str(e.id) ])
        
        print ("sending SMS")
        # clickatell rules!
        r = requests.get(url='https://platform.clickatell.com/messages/http/send?apiKey='+config.CLICKATELL_API_KEY+'==&to='+config.SMS_TO+'&content=A%20motion%20event%20ocurred.%20Sent%20from%20my%20raspberry')
    
    return "alert received"

@app.route('/status-history')
def status_history():
	s = SystemStatus.query.order_by(SystemStatus.id.desc()).all()
	return render_template('status-history.html', s=s)


# CMD to create table:
# from yourapplication import db
# db.create_all()
class Temperature(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	date = db.Column(db.String(80), unique=False, nullable=False)
	temperature = db.Column(db.String(2), unique=False, nullable=False)    
	humidity = db.Column(db.String(2), unique=False, nullable=False)

	def __repr__(self):
		return '<temperature %r>' % self.temperature


# > sqlite3:		
# CREATE TABLE event (
# 	id INTEGER PRIMARY KEY,
# 	date VARCHAR(20),
# 	type VARCHAR(100)
# );
class Event(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	date = db.Column(db.String(80), unique=False, nullable=False)
	type = db.Column(db.String(100), unique=False, nullable=False)
	seen = db.Column(db.Integer(), unique=False, nullable=True)

	def __repr__(self):
		return '<event data %r>' % self.id


class SystemStatus(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	status = db.Column(db.String(20), unique=False, nullable=False)
	date_start = db.Column(db.String(20), unique=False, nullable=False)
	date_end = db.Column(db.String(20), unique=False, nullable=False)
	pir_sensor_process_id = db.Column(db.String(20), unique=False, nullable=False)

	def __repr__(self):
		return '<system status data %r>' % self.id
	


def shutdown_server():
    # kill stream if any
    subprocess.Popen(['sudo','pkill','uv4l'])
    # kill pirsensor
    stop_pir_sensor_process()
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()

@app.route('/shutdown', methods=['GET'])
def shutdown():
    shutdown_server()
    return 'Server shutting down...'

if __name__ == '__main__':    
    app.run(host='0.0.0.0', debug=True, threaded=True)    
