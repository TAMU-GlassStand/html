#!/usr/bin/python

from smbus2 import SMBus
import RPi.GPIO as gpio
from pykeyboard import PyKeyboard
from pymouse import PyMouse
import time
import math
from subprocess import call

#create output text file for debuggin purposes
debug_output = open('/home/pi/Desktop/html/debugging.txt', 'w')

#clear any previous gpio pin setups
gpio.cleanup()

#setup gpio pins to be defined based on their pin number on the gpio header
gpio.setmode(gpio.BOARD)

#define variables used for keyboard and mouse navigations
user_location=-1 # Used to determine where the user is: 0=Settings, 1=Google Drive, 2=Removeable Storage
enter_count=0 #Used to determine number of enters pressed
zoom_count = 0 #Used to determine zoom percentage
zoom_usb = -1 #Used to determine position of selector (fit, plus, minus)
zoom_page = 0 #Temporary variable to switch buttons from zoom to next page becasue EIC board is messed up


#lux threshold for identifying whether the projector is turned on or off
lux_thresh = 500


#create the keyboard and mouse objects for doing mouse and keyboard manipulations
k = PyKeyboard()
m = PyMouse()

#define i2c bus number and i2c device addresses
busnum = 1
captivate = 0x0a
evm_address = 0x1b
amb_sense = 0x44	#address of sensor for detecting ambient light level
evm_sense = 0x45	#address of sensor for detecting projector evm light level

#list of registers on 4710 EVM
rw_reg1 = 0x36
rw_reg2 = 0x3a
resp_reg1 = 0x37
resp_reg2 = 0x3b

config = 0x10c4	#configuration bytes for opt register 0x01

#list of opcodes
disp_size=0x13	#opcode for reading display size
write_orient=0x14	#opcode for writing image orientation
read_orient=0x15	#opcode for reading image orientation
write_ctrl=0x50	#opcode for writing LED output control method
read_ctrl=0x51	#opcode for reading LED output control method
write_en=0x52	#opcode for writing RGB LED enable
read_en=0x53	#opcode for reading RGB LED enable
write_led=0x54	#opcode for writing RGB LED currents
read_led=0x55	#opcode for read RGB LED currents
read_sys=0xd1	#opcode for reading system status

#some LED current values for the 4710 EVM
#currents_max = [ 0xe0, 0x02, 0xd7, 0x03, 0xd7, 0x03 ]
#currents_mid = [ 0x44, 0x01, 0x44, 0x01, 0x44, 0x01 ]
#currents_min = [ 0x5b, 0x00, 0x5b, 0x00, 0x5b, 0x00 ]
#currents_rand= [ 0xa2, 0x01, 0xa2, 0x01, 0xa2, 0x01 ]
led_min = 91	#minimum LED current as an integer
r_max = 736	#maximum red LED current as an integer
gb_max = 983	#maximum green and blue LED current as an integer

#set delay between all i2c commands
delay = 0.1

#configure gpio pin(s) as inputs or outputs
channel1 = 11	#toggles projector on/off
channel2 = 12	#measures captivate gpio output
channel3 = 13	#measures arduino gpio output
gpio.setup(channel1, gpio.OUT, initial=gpio.HIGH)	#output gpio for toggling projector
gpio.setup(channel2, gpio.IN)	#gpio input for measuring captivate gpio output
gpio.setup(channel3, gpio.IN, pull_up_down=gpio.PUD_DOWN)	#gpio input for measuring arduino gpio output
time.sleep(1)

bus = SMBus(busnum)

#define functions for use in the script
#----------------------------------------------------------------------------------
#define function for configuring EVM projector output to rear projection mode
def evm_config(delay, evm, rw_reg, resp_reg):
	write_orient=0x14	#opcode for writing image orientation
	read_orient=0x15	#opcode for reading image orientation
	#orientation=0x6	#orientation for forward facing projection for testing
	orientation=0x4	#hex code for rear projection mode orientation
	success = 0	#keep track of whether the write was successful
	loop_count = -1
	while success==0:
		loop_count = loop_count+1
		write_count = 0
		read_count = 0
		read_redo = 1	#keep track of whether reading back of data was successful
		write_redo = 1	#keep track of whether writing to evm was successful
		while write_redo==1 and write_count<50:
			write_count = write_count + 1
			try:
				time.sleep( delay )
				bus.write_byte_data(evm, rw_reg, write_orient)
				#print("write_orient executed")
				debug_output.write("write_orient executed\n")
				time.sleep( delay )
				bus.write_byte_data(evm, write_orient, orientation)
				#print("orientation flip written to EVM")
				debug_output.write("orientation flip written to EVM\n")
				time.sleep( delay )
				write_redo = 0
			except IOError:
				#print("restarting orientation write loop")
				debug_output.write("restarting orientation write loop\n")
				continue
		while read_redo == 1 and read_count<50:
			read_count = read_count + 1
			try:
				time.sleep( delay )
				bus.write_byte_data(evm, rw_reg, read_orient)
				#print("read_orient executed")
				debug_output.write("read_orient executed\n")
				time.sleep( (1+loop_count)*delay )
				bus.write_byte_data(evm, read_orient, 0x00)
				#print("write zeros to read_orient executed")
				debug_output.write("write zeros to read_orient executed\n")
				time.sleep( delay )
				orient_read = bus.read_byte_data(evm, resp_reg)
				#print("read orientation data executed: " + hex(orient_read) )
				debug_output.write("read orientation data executed: " + hex(orient_read) +"\n")
				read_redo = 0
			except IOError:
				#print("restarting orientation read loop")
				debug_output.write("restarting orientation read loop\n")
		debug_output.write("last value of read orientation data is " + hex(orient_read) + "\n")
		debug_output.write("loop count is " + str(loop_count) )
		if orient_read == orientation:
			success = 1
		else:
			#print("orientation mismatch; restarting loop")
			debug_output.write("orientation mismatch; restarting loop\n")
			success = 0
		if loop_count >= 30:	#after too many loops, exit the loop regardless
			break
	return;
#----------------------------------------------------------------------------------
#define current reading function
def read_currents(delay, evm, rw_reg, resp_reg):
	read_led = 0x55	#opcode to read the LED currents
	resp_reg = 0x37	#address of the read response register on the EVM
	success = 0	#keep track of whether the read was successful
	loop_count = 0	#keep track of how many failed loops have occured
	while success==0:
		try:
			time.sleep(delay)
			bus.write_byte_data(evm, rw_reg, read_led)
			#print("read_led executed")
			debug_output.write("read_led executed\n")
			time.sleep(delay)
			bus.write_byte_data(evm, read_led, 0x00)
			#print("write zeros to read_led executed")
			debug_output.write("write zeros to read_led executed\n")
			time.sleep(delay)
			led_currents = bus.read_i2c_block_data(evm, resp_reg, 6)
			#print("current read executed")
			#print(led_currents)
			debug_output.write("current read executed\n")
			debug_output.write(str(led_currents) + "\n")
			success = 1
		except IOError:
			if loop_count<150:
				#print("starting over")
				debug_output.write("starting over\n")
			else:
				#print("Too many failed loops. Check that EVM is connected.")
				debug_output.write("Too many failed loops. Check that EVM is connected.\n")
				break
	return led_currents;
#----------------------------------------------------------------------------------
#define current writing function
def write_currents(delay, evm, current_list, rw_reg, resp_reg):
	write_led = 0x54	#opcode to write the LED currents
	#current_list is a 6 element list with the least significant and then most significant bytes of each color LED, red, green ,and blue
	write_redo = 1	#continue the write_led current loop if anything fails
	while write_redo == 1:
		try:
			time.sleep(delay)
			bus.write_byte_data(evm, rw_reg, write_led)
			#print("write_led executed")
			debug_output.write("write_led executed\n")
			time.sleep(delay)
			bus.write_i2c_block_data(evm, write_led, current_list)
			#print("write currents executed")
			debug_output.write("write currents executed\n")
			time.sleep(delay)
			write_redo=0
		except IOError:
			#print("restarting current write loop")
			debug_output.write("restarting current write loop\n")
			continue
		led_currents = read_currents(delay, evm, rw_reg, resp_reg)
		if led_currents==current_list:
			#print("led currents match")
			debug_output.write("led currents match\n")
			write_redo=0
		else:
			#print("led currents are mismatched; restarting loop")
			debug_output.write("led currents are mismatched; restarting loop\n")
			write_redo=1
	#print("current write executed")
	debug_output.write("current write executed")
	return;
#----------------------------------------------------------------------------------
#define light sensor configuration
def sensor_config(opt_addr):
	config = 0x10c4
	try:
		b1 = bus.write_word_data(opt_addr, 0x01, config)
		##print(b1)
		#print("Sensor configuration executed on address "+hex(opt_addr) )
		debug_output.write("Sensor configuration executed on address "+hex(opt_addr) + "\n")
	except IOError:
		#print("Configuration failed on address"+hex(opt_addr)+". Check light sensor connection.")
		debug_output.write("Configuration failed on address"+hex(opt_addr)+". Check light sensor connection.\n")
	return;
#----------------------------------------------------------------------------------
#define light sensor reading function
def light_read(delay, opt_addr):
	light_read_redo = 1
	while light_read_redo==1:
		try:
			time.sleep(delay)
			data = bus.read_word_data(opt_addr, 0)
			#print("data test1: "+data+" "+hex(data) )
			data = format(data, '016b')
			bin = data[8:16] + data[0:8]
			#print("data test "+hex(opt_addr)+": "+bin)
			exp = int( bin[0:4], 2 )
			lux = 0.01*(2**exp)*int( bin[4:16], 2)
			#print("data test "+hex(opt_addr)+": "+ str(lux) )
			debug_output.write("data test "+hex(opt_addr)+": "+ str(lux) + "\n" )
			light_read_redo = 0
		except IOError:
			#print("light sensor reading error, restarting loop")
			debug_output.write("light sensor reading error, restarting loop\n")
			light_read_redo = 1
	return lux;
#----------------------------------------------------------------------------------
#define LED current list creating function
def set_currents(r, g, b):
	currents = [ r & 0xff, r>>8, g & 0xff, g>>8, b & 0xff, b>>8]
	return currents;
#----------------------------------------------------------------------------------
#define function for reading chromium debug file to get user brightness setting
#since arguments are given default values, function can be called with no arguments
def file_read(debug_file_path = "/home/pi/bin/chrome-debug/chrome_debug.log"):
	#read all text in file then close file
	#should help avoid problem of file being written by UI while file text is
	#being analyzed
	file = open(debug_file_path, 'r') #define file to be read-only
	text = file.readlines()
	file.close()
	brightness = 0
	#create search string variable(s) to find desired data from file
	search_str = 'brightness: '
	shift = len(search_str)
	for line in text:
		if search_str in line:
			start = line.find(search_str)
			end = line.find('"',start)
			brightness = line[start+shift:end]
	return int(brightness);
#----------------------------------------------------------------------------------
#define function for turning projector on or off (like hitting the pushbutton switch)
#the gpio pin controlling the pin needs to fall LOW for at least 300ms
def projector_switch(channel):
	gpio.output(channel, gpio.HIGH)
	time.sleep(0.1)
	gpio.output(channel, gpio.LOW)
	time.sleep(1)
	gpio.output(channel, gpio.HIGH)
	return;
#----------------------------------------------------------------------------------
#define function for checking light sensor and turning projector off
#lux_thresh is the lux measurement, as measured by the light sensor, over which the
#projector evm is assumed to be projecting an image; the projector is assumed to be
#on as though the pushbutton were pressed after 
def projector_off(delay, evm_sensor, gpio_channel):
	lux = light_read(delay, evm_sensor)
	if lux>=lux_thresh:	#evm is on, so turn it off
		projector_switch(gpio_channel)
	return;
#----------------------------------------------------------------------------------
#define function for checking light sensor and turning projector on
#lux_thresh is the lux measurement, as measured by the light sensor, over which the
#projector evm is assumed to be projecting an image; the projector is assumed to be
#on as though the pushbutton were pressed after 
def projector_on(delay, evm_sensor, gpio_channel):
	lux = light_read(delay, evm_sensor)
	if lux<lux_thresh:	#evm is off, so turn it on
		projector_switch(gpio_channel)
	return;
#----------------------------------------------------------------------------------
#define user interface startup function
def start_UI():
	global user_location
	if user_location == -1:	#if UI is not open, then initialize
		k.press_key(k.shift_key)
		k.press_key(k.alt_key)
		k.tap_key('t')
		k.release_key(k.shift_key)
		k.release_key(k.alt_key)
		user_location = 0	#set user location to settings page, where UI opens
	else:
		k.press_key(k.control_key)
		k.tap_key('w')
		time.sleep(0.5)
		k.tap_key('w')
		k.release_key(k.control_key)
		user_location = -1
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
	global user_location	#Flag so buttons 2 and 3 only click if on the settings page		
	user_location = 0
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
	global user_location
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
	global user_location
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
	global user_location
	if user_location==0:
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
	global user_location
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
	global user_location
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
	global user_location
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
	global user_location
	global enter_count
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
	global user_location
	global enter_count
	if user_location==1:
		k.tap_key(k.enter_key)
		enter_count=1
	
	if user_location==2:
		k.tap_key(k.enter_key)
	return;
#----------------------------------------------------------------------------------
#define home page button (close tab)
def home_page():
	global zoom_page
	x_dim, y_dim=m.screen_size()
	x_pos=x_dim/100
	y_pos=y_dim/100

#Temporary used to repurpose from next/prev page to zoom
	if zoom_page==0:
		zoom_page=1
	else:
		zoom_page=0


	return;
#----------------------------------------------------------------------------------
#define zoom in button
def zoom_in():
	x_dim, y_dim=m.screen_size()
	x_pos=x_dim/100
	y_pos=y_dim/100
	global user_location
	global zoom_count
	global zoom_usb

	if user_location==1:
		k.press_key(k.control_key)
		k.tap_key('=')
		k.release_key(k.control_key)
		zoom_count=zoom_count+1
	
	if user_location==2:
		if zoom_usb==-1:
			k.tap_key(k.tab_key, 2)
			time.sleep(0.1)
			k.tap_key(k.tab_key, 2)
			time.sleep(0.1)
			k.tap_key(k.tab_key, 2)
			time.sleep(0.1)
			k.tap_key(k.tab_key, 2)
			time.sleep(0.1)
			k.tap_key(k.tab_key, 2)
			time.sleep(0.1)
			k.tap_key(k.tab_key, 2)
			time.sleep(0.1)
			k.tap_key(k.tab_key)
			time.sleep(0.1)
			k.tap_key(k.enter_key)
			zoom_usb=1

		if zoom_usb==0: #On the fit to page button
			k.tap_key(k.tab_key)
			k.tap_key(k.enter_key)
			zoom_usb=1

		if zoom_usb==1: #On the + button
			k.tap_key(k.enter_key)
			zoom_usb=1

		if zoom_usb==2: #On the - button
			k.press_key(k.shift_key)
			k.tap_key(k.tab_key)
			k.release_key(k.shift_key)
			k.tap_key(k.enter_key)
			zoom_usb=1

	return;
#----------------------------------------------------------------------------------
#define zoom out button
def zoom_out():
	x_dim, y_dim=m.screen_size()
	x_pos=x_dim/100
	y_pos=y_dim/100
	global user_location
	global zoom_count
	global zoom_page
	global zoom_usb

	if user_location==1:
		k.press_key(k.control_key)
		k.tap_key('-')
		k.release_key(k.control_key)
		zoom_count=zoom_count-1

	if user_location==2:
			if user_location==1 and enter_count==1 and zoom_page==0:
				k.tap_key('k')
			
			if user_location==2 and zoom_page==0:
				k.tap_key(k.left_key)
			
			if user_location==1 and zoom_page==1:
				k.press_key(k.control_key)
				k.tap_key('-')
				k.release_key(k.control_key)
				zoom_count=zoom_count-1		

			if user_location==2 and zoom_page==1:
				if zoom_usb==-1:
					k.tap_key(k.tab_key, 2)
					time.sleep(0.1)
					k.tap_key(k.tab_key, 2)
					time.sleep(0.1)
					k.tap_key(k.tab_key, 2)
					time.sleep(0.1)
					k.tap_key(k.tab_key, 2)
					time.sleep(0.1)
					k.tap_key(k.tab_key, 2)
					time.sleep(0.1)
					k.tap_key(k.tab_key, 2)
					time.sleep(0.1)
					k.tap_key(k.tab_key, 2)
					time.sleep(0.1)
					k.tap_key(k.enter_key)
					zoom_usb=2

				if zoom_usb==0: #On the fit to page button
					k.tap_key(k.tab_key, 2)
					time.sleep(0.1)
					k.tap_key(k.enter_key)
					zoom_usb=2

				if zoom_usb==1: #On the + button
					k.tap_key(k.tab_key)
					k.tap_key(k.enter_key)
					zoom_usb=2

				if zoom_usb==2: #On the - button
					k.tap_key(k.enter_key)	
					zoom_usb=2
	return;
#----------------------------------------------------------------------------------
#define previous page button
def prev_page():
	x_dim, y_dim=m.screen_size()
	x_pos=x_dim/100
	y_pos=y_dim/100
	global user_location
	global enter_count
	global zoom_page

#Zoom_page is used to repurpose buttons on broken EIC board

	if user_location==1 and zoom_page==0 and enter_count==1:
		k.tap_key('k')

	if user_location==2 and zoom_page==0:
		k.tap_key(k.left_key)


# Temporary stuff for zoom because EIC board was messed up
	if zoom_page==1:
		zoom_out()
	return;
#----------------------------------------------------------------------------------
#define next page button
def next_page():
	x_dim, y_dim=m.screen_size()
	x_pos=x_dim/100
	y_pos=y_dim/100
	global user_location
	global enter_count
	global zoom_page

#Zoom_page is used to repurpose buttons on broken EIC board
	if user_location==1 and zoom_page==0 and enter_count==1:
		k.tap_key('j')

	if user_location==2 and zoom_page==0:
		k.tap_key(k.right_key)

# Temporary stuff for zoom because EIC board was messed up
	if zoom_page==1:
		zoom_in()
	return;
#----------------------------------------------------------------------------------
#define fit to page button
def fit_page():
	x_dim, y_dim=m.screen_size()
	x_pos=x_dim/100
	y_pos=y_dim/100
	global user_location
	global zoom_count
	global zoom_usb
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
			if zoom_usb==-1:
				k.tap_key(k.tab_key, 2)
				time.sleep(0.1)
				k.tap_key(k.tab_key, 2)
				time.sleep(0.1)
				k.tap_key(k.tab_key, 1)
				k.tap_key(k.enter_key)
				zoom_usb=0

			elif zoom_usb==0: #On the fit to page button
				k.tap_key(k.enter_key)
				zoom_usb=0

			elif zoom_usb==1: #On the + button
				k.press_key(k.shift_key)
				k.tap_key(k.tab_key)
				k.release_key(k.shift_key)
				k.tap_key(k.enter_key)
				zoom_usb=0

			elif zoom_usb==2: #On the - button
				k.press_key(k.shift_key)
				k.tap_key(k.tab_key, 2)
				time.sleep(0.1)
				k.release_key(k.shift_key)
				k.tap_key(k.enter_key)
				zoom_usb=0

		
	return;
#----------------------------------------------------------------------------------
#define function for reading inputs from the captivate when the gpio interrupt occurs
def read_captivate(pause=delay, address=captivate):
	debug_output.write("read_captivate executed")
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
			#print("read unsuccessful")
			debug_output.write("read unsuccessful\n")
		
		debug_output.write(str(read) + "\n")
		#determine which button was pressed and call the appropriate function
		if touchbit==1 and read[2] != prev:
			#print(read)
			#print("user_location = " + str(user_location))
			debug_output.write(read + "\n")
			debug_output.write("user_location = " + str(user_location) + "\n")
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
#define function for reading the gpio output(s) from the arduino
#this may also be the automatic shutdown function
def auto_shutdown(pause=delay, evm_sensor=evm_sense, gpio_channel=channel1):
	k.press_key(k.control_key)
	k.tap_key('w', 2)
	k.release_key(k.control_key)
	#use the above three instructions to close the UI normally to avoid a "restore pages" pop up on next boot
	projector_off(pause, evm_sensor, gpio_channel)
	call("sudo shutdown -h now", shell=True)
	return;
#----------------------------------------------------------------------------------
#user brightness function
def autobrightness(delay, ambientinput_old, user_brightness_old, evm_address, ambient_address, rw_reg, resp_reg):

	delta=0.1	#minimum percentage change, as a decimal, in ambient light level for changes to be made
	global amb_thresh

	# read user brightness setting from folder
	user_brightness = file_read()
	if user_brightness != user_brightness_old:
		amb_thresh = light_read(delay, ambient_address)	#update the ambient lux threshold when user brightness is adjusted
	
	#Red LED Max Brightness
        red_max = 736

	#Blue LED Max Brightness
        blue_max = 983

	#Green LED Max Brightness
        green_max = 983

	#LED Currents Min
        min_current = 91

	# get light sensor reading
	ambientinput = light_read(delay, ambient_address)	

	#find what would normally be the typical rgb LED current values for the given user brightness setting
	r_norm = math.floor(min_current + float(user_brightness)/100*(red_max-min_current))
	g_norm = math.floor(min_current + float(user_brightness)/100*(green_max-min_current))
	b_norm = math.floor(min_current + float(user_brightness)/100*(blue_max-min_current))
	
	#determine if discernable change in ambient input
	if ambientinput>=ambientinput_old*(1+delta) or ambientinput<ambientinput_old*(1-delta) or user_brightness!=user_brightness_old:
		#create the current ranges for each level
		#create an adjustment for the brightness based on the log10 of the ratio of the current ambient reading and threshold reading
		adjustment = math.log10(ambientinput/amb_thresh)
		if adjustment > 1:
			adjustment = 1
		elif adjustment < -1:
			adjustment = -1
		#debug_output.write("adjustment is " + str(adjustment) + "\n")
		R = int( round(r_norm*(1+adjustment), 0) )
		G = int( round(g_norm*(1+adjustment), 0) )
		B = int( round(b_norm*(1+adjustment), 0) )
		if R > red_max:
			R = red_max
		elif R < min_current:
			R = min_current
		if G > green_max:
			G = green_max
		elif G < min_current:
			G = min_current
		if B > blue_max:
			B = blue_max
		elif B < min_current:
			B = min_current
		
		#Read current values, if match, end, if not match, change
		current_list = set_currents(R, G, B)
		led_currents = read_currents(delay, evm_address, rw_reg, resp_reg)
		if current_list != led_currents:
			write_currents(delay, evm_address, current_list, rw_reg, resp_reg)
	ambientinput_old=ambientinput
	user_brightness_old=user_brightness
	return ambientinput_old, user_brightness_old;
#----------------------------------------------------------------------------------


#configure OPT3001 sensors
sensor_config(amb_sense)
sensor_config(evm_sense)

#start 4710EVM and configure for rear projection
projector_on(delay, evm_sense, channel1)
evm_config(delay, evm_address, rw_reg1, resp_reg1)

#get the initial ambient light reading on initialization to use as initial threshold for determining if changes should be made
amb_thresh = light_read(delay, amb_sense)

#add gpio event detector interrupt for captivate inputs
gpio.add_event_detect(channel2, gpio.RISING, callback = read_captivate, bouncetime=100)

#add gpio event detector interrupt for arduino inputs
#gpio.add_event_detect(channel3, gpio.RISING, callback = auto_shutdown, bouncetime=100)

#debug_output.close()
ambientinput_old = amb_thresh
user_brightness_old = file_read()

try:
	while 1:
		#print("normal loop")
		ambientinput_old, user_brightness_old = autobrightness(delay, ambientinput_old, user_brightness_old, evm_address, amb_sense, rw_reg1, resp_reg1)
		time.sleep(5)
	
	
except KeyboardInterrupt:
	bus.close()
	gpio.cleanup()
	debug_output.close()
	#auto_shutdown(delay, evm_sense, channel3)

except Exception as ex:
	#get the type of error thrown and output it to terminal for debugging purposes
	template = "An exception of type {0} occured. Arguments:\n{1!r}"
	message = template.format( type(ex).__name__, ex.args )
	#print(message)
	debug_output.write(message)
	
	#close i2c bus and gpio resources, then shutdown
	bus.close()
	gpio.cleanup()
	debug_output.close()
	#auto_shutdown(delay, evm_sense, channel3)
