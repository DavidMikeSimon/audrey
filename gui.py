#!/usr/bin/python

from __future__ import division

import pygtk
pygtk.require('2.0')

import gtk, gobject, sys


class MainWindow:	
	def __init__(self):
		# This is necessary to make PyGTK and threads play nicely
		gobject.threads_init()
		
		# The main window
		self.window = gtk.Window(); self.window.connect("destroy", self.quit); self.window.set_title("Audrey"); self.window.set_size_request(500, 400)
		self.window.set_resizable(False); self.window.set_deletable(False); self.window.move(100, 100)
		winBox = gtk.VBox(spacing = 2); winBox.set_border_width(3); self.window.add(winBox)
		
		# Status message
		statusMsg = gtk.Label("Status"); winBox.pack_start(statusMsg)

		# Okay, we've prepared everything, let's show the window
		self.window.show_all(); self.window.set_focus(None)

	def quit(self, widget = None):
		self.window.destroy()
		gtk.main_quit()
		sys.exit() # Necessary to kill off any running threads
	

if __name__ == "__main__":
	win = MainWindow()
	gtk.main()
