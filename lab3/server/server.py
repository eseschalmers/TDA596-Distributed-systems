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
from datetime import datetime
import json
import argparse
from threading import Thread
import heapq

from bottle import Bottle, run, request, template
import requests

class BoardEntry:
	def __init__(self, id, message, last_updated, last_refreshed, is_deleted = False):
		self.id = id
		self.message = message
		self.last_updated = last_updated
		self.last_refreshed = last_refreshed
		self.is_deleted = is_deleted

	def toJson(self):
		return {
			"id": self.id,
			"message": self.message,
			"last_updated": self.last_updated.strftime('%Y-%m-%d %H:%M:%S.%f'),
			"is_deleted": self.is_deleted
		}
	
	@classmethod
	def fromJson(cls, entry):
		return cls(
			entry["id"],
			entry["message"],
			last_updated = datetime.strptime(entry["last_updated"], '%Y-%m-%d %H:%M:%S.%f'),
			last_refreshed = datetime.now(),
			is_deleted = entry["is_deleted"]
		)
# ------------------------------------------------------------------------------------------------------
try:
	app = Bottle()

	#board stores all message on the system
	# An entry is UUID : (Text, last_updated, last_refreshed)
	# board = {"0" : ("Welcome to Distributed Systems Course", datetime.now(), datetime.now())}
	board = {
			"0": BoardEntry("0", "Welcome to Distributed Systems Course", datetime(2020, 1, 1), datetime(2020, 1, 1)),
			"1": BoardEntry("1", "Test", datetime(2019, 1, 1), datetime(2019, 1, 1))
		}
	# ------------------------------------------------------------------------------------------------------
	# BOARD FUNCTIONS
	# You will probably need to modify them
	# ------------------------------------------------------------------------------------------------------
	
	#This functions will add an new element
	def add_new_element_to_store(entry):
		global board, node_id
		success = False
		try:
			if entry.id not in board.keys():
				# board[entry_sequence] = (element, latest_modification, datetime.now())
				board[entry.id] = entry
				success = True
		except Exception as e:
			print(e)
		return success

	def modify_element_in_store(entry):
		global board, node_id
		success = False
		try:
			if entry.id in board:
				if (board[entry.id].last_updated) < entry.last_updated:
					# board[entry_sequence] = (modified_element, latest_modification, datetime.now())
					board[entry.id] = entry
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
		print_board = {id:board[id].message for id in board.keys() if not board[id].is_deleted}
		return template('server/index.tpl', board_title='Vessel {}'.format(node_id),
				board_dict=sorted({"0":print_board,}.iteritems()), members_name_string='Léon Michalski, Max Sonnelid, Elias Estribeau')

	@app.get('/board')
	def get_board():
		global board, node_id
		print_board = {id:board[id].message for id in board.keys() if not board[id].is_deleted}
		return template('server/boardcontents_template.tpl',board_title='Vessel {}'.format(node_id), board_dict=sorted(print_board.iteritems()))
	
	#------------------------------------------------------------------------------------------------------
	
	# You NEED to change the follow functions
	@app.post('/board')
	def client_add_received():
		'''Adds a new element to the board
		Called directly when a user is doing a POST request on /board'''
		global board, node_id
		try:
			new_entry = BoardEntry(
				str(uuid.uuid4()),
				request.forms.get('entry'),
				datetime.now(),
				datetime.now()
			)

			success = add_new_element_to_store(new_entry)
			# Propagate action to all other nodes example :
			if success:
				# thread = Thread(target=propagate_to_vessels,
				# 				args=('/propagate/ADD/' + new_entry.id, {'entry': new_entry.toJson()}, 'POST'))
				# thread.daemon = True
				# thread.start()
				return '<h1>Successfully added entry</h1>'
		except Exception as e:
			print(e)
		return '<h1>Failed, please retry in a few seconds</hi>'

	@app.post('/board/<element_id>/')
	def client_action_received(element_id):
		success = False
		try:
			global board, node_id

			# Get the entry from the HTTP body
			delete_option = request.forms.get('delete')

			#0 = modify, 1 = delete
			new_entry = BoardEntry(
				element_id,
				request.forms.get('entry'),
				datetime.now(),
				datetime.now()
			)

			#call either delete or modify
			if (int(delete_option) == 0):
				new_entry.is_deleted = False
				action = "MODIFY"
			elif (int(delete_option) == 1):
				new_entry.is_deleted = True
				action = "DELETE"

			success = modify_element_in_store(new_entry)
			#propagate to other nodes
			if success:
				#thread = Thread(target=propagate_to_vessels,
									#args=('/propagate/' + action + "/" + str(element_id), new_entry.toJson(), 'POST'))
				#thread.daemon = True
				#thread.start()
				return '<h1>Successfully ' + action + ' entry</h1>'

		except Exception as e:
			print(e)
		return '<h1>Failed, please retry in a few seconds</h1>'	

	#With this function you handle requests from other nodes like add modify or delete
	@app.post('/propagate/<action>/<element_id>')
	def propagation_received(action, element_id):
		entry = BoardEntry.fromJson(request.json)
		print("Propagation received", entry.id, str(entry.last_updated))
		
		# Handle requests
		if action == "ADD":
			add_new_element_to_store(entry)
		# Modify the board entry
		elif action == "MODIFY" or action == "DELETE":
			modify_element_in_store(entry)
		else:
			return '<h1>Unknown action:' + action + '</h1>'
		
		return '<h1>Successfully propagated ' + action + '</h1>'

	@app.post('/propagate/sync')
	def propagation_sync():
		global board
		ids = request.forms.get('ids').split(',')
		result = {}
		for id in ids:
			r = board.get(id)
			if r is not None:
				result[id] = r.toJson()
			else:
				result[id] = None
		return result

	# ------------------------------------------------------------------------------------------------------
	# DISTRIBUTED COMMUNICATIONS FUNCTIONS
	# ------------------------------------------------------------------------------------------------------
	def contact_vessel(vessel_ip, path, payload=None, req='POST'):
		# Try to contact another server (vessel) through a POST or GET, once
		success = False
		try:
			if 'POST' in req:
				res = requests.post('http://{}{}'.format(vessel_ip, path), json=payload)
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

	def sync():
		global vessel_list, node_id, board
		next_node = (int(node_id) % len(vessel_list)) + 1# Get the next node
		next_node_ip = vessel_list[str(next_node)]
		while(True):
			time.sleep(10.0)
			try:
				payload = sorted(board.values(), key=lambda e: e.last_refreshed)[:5]

				payload = [entry.id for entry in payload]
				payload = ",".join(payload)
				payload = {"ids": payload}
				res = requests.post('http://{}/propagate/sync'.format(next_node_ip), data=payload)

				if res.status_code == 200:
					js = res.json()
					ids_to_propagate = [] # List of ids to propagate
					for id in js.keys():
						if js[id] is not None:
							entry = BoardEntry.fromJson(js[id])
							modify_element_in_store(entry)
						else:
							ids_to_propagate.append(id)
						# We have refreshed this board entry
						board[entry.id].last_refreshed = entry.last_refreshed
					for id in ids_to_propagate:
						# Propagate the entries that the next node didn't have
						contact_vessel(next_node_ip, '/propagate/ADD/{}'.format(id), board[id].toJson(), 'POST')
			except Exception as e:
				print(e)
				# The next node failed, we can propagate to the next one
				next_node = (next_node % len(vessel_list)) + 1
				next_node_ip = vessel_list[str(next_node)]

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
			thread = Thread(target=sync)
			thread.daemon = True
			thread.start()
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
