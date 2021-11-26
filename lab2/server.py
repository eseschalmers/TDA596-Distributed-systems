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
import json
import argparse
from threading import Thread

from bottle import Bottle, run, request, template
import requests
# ------------------------------------------------------------------------------------------------------
try:
    app = Bottle()

    #board stores all message on the system 
    board = {0 : "Welcome to Distributed Systems Course"} 


    # ------------------------------------------------------------------------------------------------------
    # BOARD FUNCTIONS
    # You will probably need to modify them
    # ------------------------------------------------------------------------------------------------------
    
    #This functions will add an new element
    def add_new_element_to_store(entry_sequence, element, is_propagated_call=False):
        global board, node_id
        success = False
        try:
           if entry_sequence not in board:
                board[entry_sequence] = element
                success = True
        except Exception as e:
            print(e)
        return success

    def modify_element_in_store(entry_sequence, modified_element, is_propagated_call = False):
        global board, node_id
        success = False
        try:
            if entry_sequence in board:
                board[entry_sequence] = modified_element
                success = True
        except Exception as e:
            print(e)
        return success

    def delete_element_from_store(entry_sequence, is_propagated_call = False):
        global board, node_id
        success = False
        try:
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
        global board, node_id, leader_id
        try:
            new_entry = request.forms.get('entry')
            
            success = False
            # Propagate action:
            if (node_id == leader_id):
            	print("Propagating to replicas")
                element_id = 0
                while (element_id in board):
                    element_id = element_id + 1
                success = add_new_element_to_store(element_id, new_entry)

                if success:
                	# Propagate to all the replicas
                	thread = Thread(target=propagate_to_vessels,
                		args=('/propagate/ADD/{}'.format(element_id), {'entry': new_entry}, 'POST'))
                	thread.daemon = True
                	thread.start()
            else:
            	print("Propagating to leader")
            	success = propagate_to_leader(
            		path='/propagate/ADD/-1',
            		payload={'entry': new_entry},
            		req='POST'
            	)

            if success:
            	return '<h1>Successfully added entry</h1>'
            else:
            	return '<h1>Failed, please retry in a few seconds</hi>'
        except Exception as e:
            print(e)
        return False

    @app.post('/board/<element_id:int>/')
    def client_action_received(element_id):
        try:
            global board, node_id, leader_id
            
            # Get the entry from the HTTP body
            entry = request.forms.get('entry')
            
            delete_option = request.forms.get('delete') 
	        #0 = modify, 1 = delete
            
            #call either delete or modify
            if (int(delete_option) == 0):
                action = "MODIFY"
            elif (int(delete_option) == 1):
                action = "DELETE"
            
            #propagate to other nodes
            success = False
            if (node_id == leader_id):
                if action == "MODIFY":
                	success = modify_element_in_store(element_id, entry, False)
                elif action == "DELETE":
                	success = delete_element_from_store(element_id, False)

                if success: # Do not propagate if the action failed
                	thread = Thread(target=propagate_to_vessels,
                                	args=('/propagate/{}/{}'.format(action, element_id), {'entry': entry}, 'POST'))
                	thread.daemon = True
                	thread.start()
            else:
            	print("Propagating to leader")
            	success = propagate_to_leader(
            		path='/propagate/{}/{}'.format(action, element_id),
            		payload={'entry': entry},
            		req='POST'
            	)

            if success:
            	return '<h1>Successfully ' + action + ' entry</h1>'
            else:
            	return '<h1>Failed, please retry in a few seconds</h1>'	
        except Exception as e:
            print(e)
        return False

    #With this function you handle requests from other nodes like add modify or delete
    @app.post('/propagate/<action>/<element_id:int>')
    def propagation_received(action, element_id):
        global node_id, board, leader_id
        
	    #get entry from http body
        entry = request.forms.get('entry')
        
        # Handle requests
        if action == "ADD":
            if (element_id == -1): # This add request is coming from one of the replicas
            	element_id = 0
            	while (element_id in board):
            		element_id = element_id + 1
                    
            add_new_element_to_store(element_id, entry, True)
        # Modify the board entry
        elif action == "MODIFY":
            modify_element_in_store(element_id, entry, True)
        # Delete the entry from the board
        elif action == "DELETE":
            delete_element_from_store(element_id, True)
        else:
            return False
            
        if (node_id == leader_id):
            thread = Thread(target=propagate_to_vessels,
                                args=('/propagate/{}/{}'.format(action, element_id), {'entry': entry}, 'POST'))
            thread.daemon = True
            thread.start()

        return '<h1>Successfully propagated ' + action + '</h1>'


    @app.get('/election/started')
    def election_started():
    	thread = Thread(target=start_election)
    	thread.daemon = True
    	thread.start()
    	return '<h1>Election started</h1>'


    @app.post('/election/success/<leader:int>')
    def election_successful(leader):
     	global leader_id
     	leader_id = leader
     	print('NEW LEADER IS : {}'.format(leader_id))
     	return '<h1>Leader changed</h1>'

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

            if res.status_code == 200:
                success = True
        except Exception as e:
        	print(e)
        return success

	
    def propagate_to_leader(path, payload = None, req = 'POST'):
        global vessel_list, node_id, leader_id
        
        success = contact_vessel(vessel_list[str(leader_id)], path, payload, req)
            
        if not success:
            print("\n\nCould not contact leader : id={}, ip={}\n\n".format(leader_id, vessel_list[str(leader_id)]))
            print("Let's initiate LEADER ELECTION!")

            thread = Thread(target=start_election)
            thread.daemon = True
            thread.start()

        return success


    def propagate_to_vessels(path, payload = None, req = 'POST'):
        """
        Propagate a message to all the replicas.
        This should only be called by the current leader.
        """
        global vessel_list, node_id, leader_id

        for vessel_id, vessel_ip in vessel_list.items():
            if vessel_id != str(node_id): # don't propagate to yourself
                success = contact_vessel(vessel_ip, path, payload, req)
                if not success:
                    print("\n\nCould not contact vessel {}\n\n".format(vessel_id))

    def start_election():
    	global vessel_list, node_id, leader_id
    	is_new_leader = True # Assume that we are the new leader
    	for vessel_id, vessel_ip in vessel_list.items():
    		if int(vessel_id) > node_id and is_new_leader:
    			try:
	    			res = contact_vessel(
	    				vessel_ip=vessel_ip,
	    				path='/election/started',
	    				req='GET'
	    			)
	    			if res == True:
	    				is_new_leader = False
	    				break
    			except Exception as e:
    				print("Could not contact node {} during election process".format(vessel_id))
    				print(e)

    	# if is_new_leader == True, we could not contact nodes with higher id
    	if is_new_leader:
     		leader_id = node_id
     		thread = Thread(target=propagate_new_leader, args=(node_id,))
     		thread.daemon = True
     		thread.start()
     	return is_new_leader

    def propagate_new_leader(id):
    	global vessel_list, node_id

    	for vessel_id, vessel_ip in vessel_list.items():
    		if vessel_id != str(node_id):
    			contact_vessel(vessel_ip, '/election/success/' + str(id), req='POST')

    # ------------------------------------------------------------------------------------------------------
    # EXECUTION
    # ------------------------------------------------------------------------------------------------------
    def main():
        global vessel_list, node_id, app, leader_id

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

        leader_id = 1
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
