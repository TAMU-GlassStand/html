#!/usr/bin/python

from smbus2 import SMBus
import RPi.GPIO as gpio
from pykeyboard import PyKeyboard
from pymouse import PyMouse
import time
import math
from subprocess import call

#clear any previous gpio pin setups
gpio.cleanup()

#setup gpio pins to be defined based on their pin number on the gpio header
gpio.setmode(gpio.BOARD)

#create the keyboard and mouse objects for doing mouse and keyboard manipulations
k = PyKeyboard()
m = PyMouse()

#configure gpio pin(s) as inputs or outputs
channel1 = 11	#toggles projector on/off
channel2 = 12	#measures captivate gpio output
channel3 = 13	#measures arduino gpio output
gpio.setup(channel1, gpio.OUT, initial=gpio.HIGH)	#output gpio for toggling projector
gpio.setup(channel2, gpio.IN)	#gpio input for measuring captivate gpio output
gpio.setup(channel3, gpio.IN, pull_up_down=gpio.PUD_DOWN)	#gpio input for measuring arduino gpio output
time.sleep(1)

delay = 0.1

lux_thresh = 500

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

bus = SMBus(busnum)

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
			light_read_redo = 0
		except IOError:
			#print("light sensor reading error, restarting loop")
			light_read_redo = 1
	return lux;
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
#define function for reading the gpio output(s) from the arduino
#this may also be the automatic shutdown function
def auto_shutdown(pause=delay, evm_sensor=evm_sense, gpio_channel=channel1):
	k.press_key(k.control_key)
	k.tap_key('w', 2)
	k.release_key(k.control_key)
	#use the above three instructions to close the UI normally to avoid a "restore pages" pop up on next boot
	projector_switch(gpio_channel)
	call("sudo shutdown -h now", shell=True)
	return;
#----------------------------------------------------------------------------------

auto_shutdown()

