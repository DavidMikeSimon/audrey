#!/usr/bin/python

from __future__ import division

import pygtk
pygtk.require('2.0')

import gtk, gobject, sys

from lib import *


class MainWindow:	
	def __init__(self):
		# This is necessary to make PyGTK and threads play nicely
		gobject.threads_init()
		
		# Create and start the AudreyController
		self.controller = AudreyController()
		self.controller.start()
		
		# The main window
		self.window = gtk.Window(); self.window.connect("destroy", self.quit); self.window.set_title("Audrey"); self.window.set_size_request(500, 400)
		self.window.set_resizable(False); self.window.set_deletable(False); self.window.set_modal(False); self.window.move(100, 100)
		winBox = gtk.VBox(spacing = 2); winBox.set_border_width(3); self.window.add(winBox)
		
		# Status message
		self.statusMsg = gtk.Label("Status"); self.statusMsg.set_line_wrap(True); winBox.pack_start(self.statusMsg)

		# The 'Eat!' button
		self.eatBtn = gtk.Button("Eat!"); self.eatBtn.connect("clicked", self.eatClicked); winBox.pack_start(self.eatBtn, expand = False, padding = 30)
		
		# Run the tick method every 50 ms
		gobject.timeout_add(50, self.tick)
		
		# Okay, we've prepared everything, let's show the window
		self.window.show_all(); self.window.set_focus(None)
	
	def eatClicked(self, widget):
		self.controller.pushEvent("EatButtonPushed")
	
	def tick(self):
		try:
			self.window.deiconify() # Dumb trick to keep the window from iconifying. There must be a better way to do this, but I can't find it.
			statusMsg = self.controller.pump()
			self.statusMsg.set_text(statusMsg)
			return True
		except:
			self.quit()
	
	def quit(self, widget = None):
		self.window.destroy()
		gtk.main_quit()
		sys.exit() # Necessary to kill off any running threads/subprocesses


if __name__ == "__main__":
	win = MainWindow()
	try:
		gtk.main()
	except:
		sys.exit()
