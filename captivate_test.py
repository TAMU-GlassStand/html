#!/usr/bin/python

from pykeyboard import PyKeyboard
from pymouse import PyMouse
from smbus2 import SMBus
import time
import RPi.GPIO as gpio

#create the keyboard and mouse objects for doing mouse and keyboard manipulations
k = PyKeyboard()
m = PyMouse()

#setup gpio pins to be defined based on their pin number on the gpio header
gpio.setmode(gpio.BOARD)

#define variables used for keyboard and mouse navigations
user_location = -1 # Used to determine where the user is: 0=Settings, 1=Google Drive, 2=Removeable Storage
enter_count = 0 #Used to determine number of enters pressed
zoom_count = 0 #Used to determine zoom percentage

#define i2c bus number and i2c device addresses
busnum = 1
captivate = 0x0a
evm_address = 0x1b
amb_sense = 0x44	#address of sensor for detecting ambient light level
evm_sense = 0x45	#address of sensor for detecting projector evm light level

#configure gpio pin(s) as inputs or outputs
channel1 = 11
channel2 = 12
channel3 = 13
gpio.setup(channel1, gpio.OUT, initial=gpio.HIGH)	#output gpio for toggling projector
gpio.setup(channel2, gpio.IN)	#gpio input for measuring captivate gpio output
gpio.setup(channel3, gpio.IN)	#gpio input for measuring arduino gpio output

bus = SMBus(busnum)
delay = 0.1

#-----------------------------------------------------------------
#define function for reading chromium debug file to get user brightness setting
#since arguments are given default values, function can be called with no arguments
def file_read(search_str='brightness: ', debug_file_path = "/home/pi/bin/chrome-debug/chrome_debug.log"):
	#read all text in file then close file
	#should help avoid problem of file being written by UI while file text is
	#being analyzed
	file = open(debug_file_path, 'r') #define file to be read-only
	text = file.readlines()
	file.close()
	#create search string variable(s) to find desired data from file
	#search_str = 'brightness: '
	shift = len(search_str)
	for line in text:
		if search_str in line:
			start = line.find(search_str)
			end = line.find('"',start)
			data = line[start+shift:end]
	print(search_str + data)
	return int(data);
#-----------------------------------------------------------------
#define user interface startup function
def start_UI():
	k.press_key(k.shift_key)
	k.press_key(k.alt_key)
	k.tap_key('t')
	k.release_key(k.shift_key)
	k.release_key(k.alt_key)	
	return;
#----------------------------------------------------------------------------------
#define function for closing all windows in user interface
def close_window():
	k.press_key(k.alt_key)
	k.tap_key(k.function_keys[4])
	k.release_key(k.alt_key)	
	return;
#----------------------------------------------------------------------------------
#define setttings button
def settings_page():
	x_dim, y_dim=m.screen_size()
	x_pos=x_dim/100
	y_pos=y_dim/100
	m.move(x_pos*9, y_pos*15)
	m.click(x_pos*9, y_pos*15, 1)
	user_location=0	#Flag so buttons 2 and 3 only click if on the settings page		

	return;
#----------------------------------------------------------------------------------
#define google drive button
def google_page():
	x_dim, y_dim=m.screen_size()
	x_pos=x_dim/100
	y_pos=y_dim/100
	# Google Drive
	m.move(x_pos*9, y_pos*45)
	m.click(x_pos*9, y_pos*45, 1)
	user_location=1
	time.sleep(1.5)
	k.tap_key(k.tab_key, 3)

	return;
#----------------------------------------------------------------------------------
#define removable storage button
def removable_page():
	x_dim, y_dim=m.screen_size()
	x_pos=x_dim/100
	y_pos=y_dim/100
	m.move(x_pos*9, y_pos*80)
	m.click(x_pos*9, y_pos*80)
	user_location=2
	time.sleep(1)
	k.tap_key(k.tab_key)

	return;
#----------------------------------------------------------------------------------
#define brightness increase button
def bright_up():
	x_dim, y_dim=m.screen_size()
	x_pos=x_dim/100
	y_pos=y_dim/100
	if file_read('user_location: ')==0:
		# Brightness Plus
		m.move(x_pos*30, y_pos*21.25)
		m.click(x_pos*30, y_pos*21.25, 1)

		# Apply Changes  
		m.move(x_pos*26, y_pos*22.5)
		m.click(x_pos*26, y_pos*22.5, 1)


	return;
#----------------------------------------------------------------------------------
#define brightness decrease button
def bright_down():
	x_dim, y_dim=m.screen_size()
	x_pos=x_dim/100
	y_pos=y_dim/100
	if user_location==0:
		# Brightness Minus
		m.move(x_pos*35.25, y_pos*21.25)
		m.click(x_pos*35.25, y_pos*21.25, 1)

		# Apply Changes
		m.move(x_pos*26, y_pos*22.5)
		m.click(x_pos*26, y_pos*22.5, 1)

	return;
#----------------------------------------------------------------------------------
#define tab backward (up) button
def tab_back():
	x_dim, y_dim=m.screen_size()
	x_pos=x_dim/100
	y_pos=y_dim/100
	if user_location==1:
		k.press_key(k.shift_key)
		k.tap_key(k.tab_key, 2)
		k.release_key(k.shift_key)
	
	elif user_location==2:
		k.press_key(k.shift_key)
		k.tap_key(k.tab_key)
		k.release_key(k.shift_key)
	return;
#----------------------------------------------------------------------------------
#define tab forward (down) button
def tab_forward():
	x_dim, y_dim=m.screen_size()
	x_pos=x_dim/100
	y_pos=y_dim/100
	if user_location==1:
		k.tap_key(k.tab_key, 2)

	elif user_location==2:
		k.tap_key(k.tab_key)
	return;
#----------------------------------------------------------------------------------
#define page back button
def page_back():
	x_dim, y_dim=m.screen_size()
	x_pos=x_dim/100
	y_pos=y_dim/100
	if user_location==1 and enter_count==1:
		k.press_key(k.control_key)
		k.tap_key('w')
		k.release_key(k.control_key)
		enter_count=0
		
	if user_location==2:
		k.press_key(k.alt_key)
		k.tap_key(k.left_key)
		k.release_key(k.alt_key)
		enter_count=0
	return;
#----------------------------------------------------------------------------------
#define enter button
def enter_button():
	x_dim, y_dim=m.screen_size()
	x_pos=x_dim/100
	y_pos=y_dim/100
	if user_location==1:
		k.tap_key(k.enter_key)
		enter_count=1
	
	if user_location==2:
		k.tap_key(k.enter_key)
	return;
#----------------------------------------------------------------------------------
#define home page button (close tab)
def home_page():
	x_dim, y_dim=m.screen_size()
	x_pos=x_dim/100
	y_pos=y_dim/100
	return;
#----------------------------------------------------------------------------------
#define zoom in button
def zoom_in():
	x_dim, y_dim=m.screen_size()
	x_pos=x_dim/100
	y_pos=y_dim/100

	if user_location==1:
		k.press_key(k.control_key)
		k.tap_key('=')
		k.release_key(k.control_key)
		zoom_count=zoom_count+1
	
#	if user_location==2: Still working on zoom for removable storage

	return;
#----------------------------------------------------------------------------------
#define zoom out button
def zoom_out():
	x_dim, y_dim=m.screen_size()
	x_pos=x_dim/100
	y_pos=y_dim/100
	
	if user_location==1:
		k.press_key(k.control_key)
		k.tap_key('-')
		k.release_key(k.control_key)
		zoom_count=zoom_count-1

#	if user_location==2: Still working on zoom for removable storage
	return;
#----------------------------------------------------------------------------------
#define previous page button
def prev_page():
	x_dim, y_dim=m.screen_size()
	x_pos=x_dim/100
	y_pos=y_dim/100

	if user_location==1 and enter_count==1:
		k.tap_key('k')

	if user_location==2:
		k.tap_key(k.left_key)
	return;
#----------------------------------------------------------------------------------
#define next page button
def next_page():
	x_dim, y_dim=m.screen_size()
	x_pos=x_dim/100
	y_pos=y_dim/100

	if user_location==1 and enter_count==1:
		k.tap_key('j')

	if user_location==2:
		k.tap_key(k.right_key)
	return;
#----------------------------------------------------------------------------------
#define fit to page button
def fit_page():
	x_dim, y_dim=m.screen_size()
	x_pos=x_dim/100
	y_pos=y_dim/100

	#Could also use ctrl+0 to restore zoom

	if user_location==1 and zoom_count>0:
		while zoom_count>0:
			k.press_key(k.control_key)
			k.tap_key('-')
			k.release_key(k.control_key)
			zoom_count=zoom_count-1

	if user_location==1 and zoom_count<0:
		while zoom_count<0:
			k.press_key(k.control_key)
			k.tap_key('=')
			k.release_key(k.control_key)
			zoom_count=zoom_count+1

	if user_location==2:
		time.sleep(0.1)

		
	return;
#----------------------------------------------------------------------------------
#define function for reading inputs from the captivate when the gpio interrupt occurs
def read_captivate(pause=delay, address=captivate):

	prev = -1
	#define button values
	start = 0
	settings = 5
	google = 9
	removable = 13
	bright_plus = 2
	bright_minus = 12
	tab_back_up = 8
	tab_forward_down = 11
	back = 4
	enter = 7
	home = 1
	zoomin = 14
	zoomout = 15
	prev_pg = 6
	next_pg = 3
	fit_to_page = 10

	while gpio.input(channel2)==1:
		data0 = [0, 0, 0, 0, 0, 0]
		try:
			bus.write_i2c_block_data(address, 0x00, data0)
			#time.sleep(pause)
			read = bus.read_i2c_block_data(address, 0x00, 6)
			#byte 3 (read[2]) changes based on button being pressed
			#byte 6 (read[5]) changes when touch/proximity is detected
			touchbit = read[5] & 0x01
			button = read[2]
		except IOError:
			print("read unsuccessful")
		
		#determine which button was pressed and call the appropriate function
		if touchbit==1 and read[2] != prev:
			print(read)
			print("user_location = " + str(user_location))
			prev = read[2]
			touchbit=-1

			if button == start:
				start_UI()
			elif button == settings:
				settings_page()
			elif button == google:
				google_page()
			elif button == removable:
				removable_page()
			elif button == bright_plus:
				bright_up()
			elif button == bright_minus:
				bright_down()
			elif button == tab_back_up:
				tab_back()
			elif button == tab_forward_down:
				tab_forward()
			elif button == back:
				page_back()
			elif button == enter:
				enter_button()
			elif button == home:
				home_page()
			elif button == zoomin:
				zoom_in()
			elif button == zoomout:
				zoom_out()
			elif button == prev_pg:
				prev_page()
			elif button == next_pg:
				next_page()
			elif button == fit_to_page:
				fit_page()
		elif touchbit == 0:
			prev = -1
	return;
#----------------------------------------------------------------------------------

try:
	while True:
		read_captivate()
except KeyboardInterrupt:
	bus.close()
	gpio.cleanup()
except Exception as ex:
	#get the type of error thrown and output it to terminal for debugging purposes
	template = "An exception of type {0} occured. Arguments:\n{1!r}"
	message = template.format( type(ex).__name__, ex.args )
	print(message)
	
	#close i2c bus and gpio resources, then shutdown
	bus.close()
	gpio.cleanup()
