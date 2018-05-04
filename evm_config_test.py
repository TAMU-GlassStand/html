#!/usr/bin/python

from smbus2 import SMBus
import RPi.GPIO as gpio
from pykeyboard import PyKeyboard
from pymouse import PyMouse
import time
import math
from subprocess import call

#clear any previous gpio pin setups
#gpio.cleanup()

#setup gpio pins to be defined based on their pin number on the gpio header
gpio.setmode(gpio.BOARD)

#define variables used for keyboard and mouse navigations
user_location=-1 # Used to determine where the user is: 0=Settings, 1=Google Drive, 2=Removeable Storage
enter_count=0 #Used to determine number of enters pressed
zoom_count = 0 #Used to determine zoom percentage
zoom_usb = -1 #Used to determine position of selector (fit, plus, minus)
zoom_page = 0 #Temporary variable to switch buttons from zoom to next page becasue EIC board is messed up


#lux threshold for identifying whether the projector is turned on or off
lux_thresh = 150


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
delay = 0.1


#configure gpio pin(s) as inputs or outputs
channel1 = 11
channel2 = 12
channel3 = 13
gpio.setup(channel1, gpio.OUT, initial=gpio.HIGH)	#output gpio for toggling projector
gpio.setup(channel2, gpio.IN)	#gpio input for measuring captivate gpio output
gpio.setup(channel3, gpio.IN, pull_up_down=gpio.PUD_DOWN)	#gpio input for measuring arduino gpio output


bus = SMBus(busnum)


#define functions for use in the script
#----------------------------------------------------------------------------------
#define function for configuring EVM projector output to rear projection mode
def evm_config(delay, evm, rw_reg, resp_reg):
	write_orient=0x14	#opcode for writing image orientation
	read_orient=0x15	#opcode for reading image orientation
	orientation=0x06	#orientation for forward facing projection for testing
	#orientation=0x04	#hex code for rear projection mode orientation
	success = 0	#keep track of whether the write was successful
	read_redo = 1	#keep track of whether reading back of data was successful
	while success==0:
		try:
			time.sleep(delay)
			bus.write_byte_data(evm, rw_reg, write_orient)
			print("write_orient executed")
			time.sleep(delay)
			bus.write_byte_data(evm, write_orient, orientation)
			print("orientation flip written to EVM")
			time.sleep(delay)
		except IOError:
			print("restarting orientation write loop")
			continue
		while read_redo == 1:
			try:
				time.sleep(delay)
				bus.write_byte_data(evm, rw_reg, read_orient)
				print("read_orient executed")
				time.sleep(delay)
				bus.write_byte_data(evm, read_orient, 0x00)
				print("write zeros to read_orient executed")
				time.sleep(delay)
				orient_read = bus.read_byte_data(evm, resp_reg)
				print("read orientation data executed: " + hex(orient_read) )
				read_redo = 0
			except IOError:
				print("restarting orientation read loop")
		if orient_read == orientation:
			success = 1
		else:
			print("orientation mismatch; restarting loop")
			success = 0
			
	return;
#-----------------------------------------------------------------------------
#define light sensor configuration
def sensor_config(opt_addr):
	config = 0x10c4
	try:
		b1 = bus.write_word_data(opt_addr, 0x01, config)
		#print(b1)
		print("Sensor configuration executed on address "+hex(opt_addr) )
	except IOError:
		print("Configuration failed on address"+hex(opt_addr)+". Check light sensor connection.")
	return;
#----------------------------------------------------------------------------------
#define light sensor reading function
def light_read(delay, opt_addr):
	light_read_redo = 1
	while light_read_redo==1:
		try:
			time.sleep(delay)
			data = bus.read_word_data(opt_addr, 0)
			# print("data test1: "+data+" "+hex(data) )
			data = format(data, '016b')
			bin = data[8:16] + data[0:8]
			# print("data test "+hex(opt_addr)+": "+bin)
			exp = int( bin[0:4], 2 )
			lux = 0.01*(2**exp)*int( bin[4:16], 2)
			print("data test "+hex(opt_addr)+": "+ str(lux) )
			light_read_redo = 0
		except IOError:
			print("light sensor reading error, restarting loop")
			light_read_redo = 1
	return lux;
#----------------------------------------------------------------------------------
#define LED current list creating function
def set_currents(r, g, b):
	currents = [ r & 0xff, r>>8, gb & 0xff, gb>>8, gb & 0xff, gb>>8]
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
	time.sleep(0.4)
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

#configure OPT3001 sensors
sensor_config(amb_sense)
sensor_config(evm_sense)

#start 4710EVM and configure for rear projection
projector_on(delay, evm_sense, channel1)
evm_config(delay, evm_address, rw_reg1, resp_reg1)
