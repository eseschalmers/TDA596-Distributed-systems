# coding=utf-8
# ------------------------------------------------------------------------------------------------------
# TDA596 - Lab 1
# server/server.py
# Input: Node_ID total_number_of_ID
# Student: Léon Michalski, Max Sonnelid, Elias Estribeau
# ------------------------------------------------------------------------------------------------------
import traceback
import sys
import time
import uuid
import datetime
import json
import argparse
from threading import Thread

from bottle import Bottle, run, request, template
import requests
# ------------------------------------------------------------------------------------------------------
try:
	app = Bottle()

	#board stores all message on the system
	board = {"0" : ("Welcome to Distributed Systems Course", datetime.datetime.now())} 

	# ------------------------------------------------------------------------------------------------------
	# BOARD FUNCTIONS
	# You will probably need to modify them
	# ------------------------------------------------------------------------------------------------------
	
	#This functions will add an new element
	def add_new_element_to_store(entry_sequence, element, latest_modification, is_propagated_call=False):
		global board, node_id
		success = False
		try:
			if entry_sequence not in board:
				board[entry_sequence] = (element, latest_modification)
				success = True
		except Exception as e:
			print(e)
		return success

	def modify_element_in_store(entry_sequence, modified_element, latest_modification, is_propagated_call = False):
		global board, node_id
		success = False
		try:
			if entry_sequence in board:
				if (board[entry_sequence][1] + datetime.timedelta(seconds=20)) < latest_modification:
					board[entry_sequence] = (modified_element, latest_modification)
					success = True
		except Exception as e:
			print(e)
		return success

	def delete_element_from_store(entry_sequence, latest_modification, is_propagated_call = False):
		global board, node_id
		success = False
		try:
			if (board[entry_sequence][1] + datetime.timedelta(seconds=20)) < latest_modification:
				board.pop(entry_sequence)
				success = True
		except Exception as e:
			print(e)
		return success

	# ------------------------------------------------------------------------------------------------------
	# ROUTES
	# ------------------------------------------------------------------------------------------------------
	# a single example (index) for get, and one for post
	# ------------------------------------------------------------------------------------------------------
	#No need to modify this
	@app.route('/')
	def index():
		global board, node_id
		return template('server/index.tpl', board_title='Vessel {}'.format(node_id),
				board_dict=sorted({"0":board,}.iteritems()), members_name_string='Léon Michalski, Max Sonnelid, Elias Estribeau')

	@app.get('/board')
	def get_board():
		global board, node_id
		print(board)
		return template('server/boardcontents_template.tpl',board_title='Vessel {}'.format(node_id), board_dict=sorted(board.iteritems()))
	
	#------------------------------------------------------------------------------------------------------
	
	# You NEED to change the follow functions
	@app.post('/board')
	def client_add_received():
		'''Adds a new element to the board
		Called directly when a user is doing a POST request on /board'''
		global board, node_id
		try:
			new_entry = request.forms.get('entry')
			
			element_id = 0
			latest_modification = datetime.datetime.now()
		   
			while (element_id in board):
				element_id = element_id + 1

			element_id = str(uuid.uuid4())

			add_new_element_to_store(element_id, new_entry, latest_modification)

			# Propagate action to all other nodes example :
			thread = Thread(target=propagate_to_vessels,
							args=('/propagate/ADD/' + str(element_id), {'entry': new_entry, 'latest_modification': str(latest_modification)}, 'POST'))
			thread.daemon = True
			thread.start()
			return '<h1>Successfully added entry</h1>'
		except Exception as e:
			print(e)
		return '<h1>Failed, please retry in a few seconds</hi>'

	@app.post('/board/<element_id>/')
	def client_action_received(element_id):
		success = False
		try:
			global board, node_id

			print("You receive an element", element_id)
			print("id is ", node_id)

			# Get the entry from the HTTP body
			entry = request.forms.get('entry')
			latest_modification = datetime.datetime.now()
			delete_option = request.forms.get('delete')

			#0 = modify, 1 = delete

			print("Client action", entry, str(latest_modification))

			#call either delete or modify
			if (int(delete_option) == 0):
				success = modify_element_in_store(element_id, entry, latest_modification, False)
				action = "MODIFY"

			if (int(delete_option) == 1):
				success = delete_element_from_store(element_id, latest_modification, False)
				action = "DELETE"

			#propagate to other nodes
			thread = Thread(target=propagate_to_vessels,
								args=('/propagate/' + action + "/" + str(element_id), {'entry': entry, 'latest_modification': str(latest_modification)}, 'POST'))
			thread.daemon = True
			thread.start()
		except Exception as e:
			print(e)
		if success:
			return '<h1>Successfully ' + action + ' entry</h1>'
		else:
			return '<h1>Failed, please retry in a few seconds</h1>'	

	#With this function you handle requests from other nodes like add modify or delete
	@app.post('/propagate/<action>/<element_id>')
	def propagation_received(action, element_id):
		#get entry from http body
		entry = request.forms.get('entry')
		latest_modification = datetime.datetime.strptime(request.forms.get('latest_modification'), '%Y-%m-%d %H:%M:%S.%f')
		print("the action is", action)

		print("Propagation received", entry, str(latest_modification))
		
		# Handle requests
		if action == "ADD":
			add_new_element_to_store(element_id, entry, latest_modification, True)
		# Modify the board entry
		elif action == "MODIFY":
			modify_element_in_store(element_id, entry, latest_modification, True)
		# Delete the entry from the board
		elif "DELETE":
			delete_element_from_store(element_id, latest_modification, True)
		else:
			return '<h1>Unknown action:' + action + '</h1>'
		
		return '<h1>Successfully propagated ' + action + '</h1>'


	# ------------------------------------------------------------------------------------------------------
	# DISTRIBUTED COMMUNICATIONS FUNCTIONS
	# ------------------------------------------------------------------------------------------------------
	def contact_vessel(vessel_ip, path, payload=None, req='POST'):
		# Try to contact another server (vessel) through a POST or GET, once
		success = False
		try:
			if 'POST' in req:
				res = requests.post('http://{}{}'.format(vessel_ip, path), data=payload)
			elif 'GET' in req:
				res = requests.get('http://{}{}'.format(vessel_ip, path))
			else:
				print('Non implemented feature!')
			# result is in res.text or res.json()
			print(res.text)
			if res.status_code == 200:
				success = True
		except Exception as e:
			print(e)
		return success

	def propagate_to_vessels(path, payload = None, req = 'POST'):
		global vessel_list, node_id

		for vessel_id, vessel_ip in vessel_list.items():
			if int(vessel_id) != node_id: # don't propagate to yourself
				success = contact_vessel(vessel_ip, path, payload, req)
				if not success:
					print("\n\nCould not contact vessel {}\n\n".format(vessel_id))

		
	# ------------------------------------------------------------------------------------------------------
	# EXECUTION
	# ------------------------------------------------------------------------------------------------------
	def main():
		global vessel_list, node_id, app

		port = 80
		parser = argparse.ArgumentParser(description='Your own implementation of the distributed blackboard')
		parser.add_argument('--id', nargs='?', dest='nid', default=1, type=int, help='This server ID')
		parser.add_argument('--vessels', nargs='?', dest='nbv', default=1, type=int, help='The total number of vessels present in the system')
		args = parser.parse_args()
		node_id = args.nid
		vessel_list = dict()
		# We need to write the other vessels IP, based on the knowledge of their number
		for i in range(1, args.nbv+1):
			vessel_list[str(i)] = '10.1.0.{}'.format(str(i))

		try:
			run(app, host=vessel_list[str(node_id)], port=port)
		except Exception as e:
			print(e)
	# ------------------------------------------------------------------------------------------------------
	if __name__ == '__main__':
		main()
		
		
except Exception as e:
		traceback.print_exc()
		while True:
			time.sleep(60.)
