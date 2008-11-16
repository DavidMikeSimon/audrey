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
		self.window = gtk.Window(); self.window.connect("destroy", self.quit); self.window.set_title("Audrey"); self.window.set_size_request(750, 550)
		winBox = gtk.VBox(spacing = 2); winBox.set_border_width(3); self.window.add(winBox)
		
		# Menu bar
		menuBar = gtk.MenuBar(); winBox.pack_start(menuBar, expand = False)
		
		# File menu
		fileMenuItem = gtk.MenuItem("_File"); menuBar.append(fileMenuItem)
		fileMenu = gtk.Menu(); fileMenuItem.set_submenu(fileMenu)
		fileQuit = gtk.ImageMenuItem(gtk.STOCK_QUIT); fileQuit.connect("activate", self.quit); fileMenu.append(fileQuit)
		
		# The content frame
		contentRow = gtk.HBox();  winBox.pack_start(contentRow)
		contentFrame = gtk.Frame(); contentFrame.set_size_request(-1, 300); contentRow.pack_start(contentFrame)
		self.contentBox = gtk.EventBox(); self.contentBox.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse("#FFFFFF")); contentFrame.add(self.contentBox)
		
		# Okay, we've prepared everything, let's show the window
		self.window.show_all(); self.window.set_focus(None)

	def quit(self, widget = None):
		self.window.destroy()
		gtk.main_quit()
		sys.exit() # Necessary to kill off any running threads
	

if __name__ == "__main__":
	win = MainWindow()
	gtk.main()
