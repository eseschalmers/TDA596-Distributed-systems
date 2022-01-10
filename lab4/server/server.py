# coding=utf-8
# ------------------------------------------------------------------------------------------------------
# TDA596 - Lab 1
# server/server.py
# Input: Node_ID total_number_of_ID
# Student: Léon Michalski, Max Sonnelid, Elias Estribeau
# ------------------------------------------------------------------------------------------------------
import traceback
import time
import argparse
from threading import Thread

from bottle import Bottle, run, request, template
import requests
# ------------------------------------------------------------------------------------------------------
try:
    app = Bottle()

    #board stores all message on the system 
    board = {0 : "Welcome to Distributed Systems Course"} 
    vote_dict = {}   #Vote vector storing all incoming votes in phase 1
    vectors = {}   #Dictionary storing all incoming vote vectors in phase 2
    byz_node = False   #Boolean describing if a node is byzantine or not
    no_loyal = 3  #Number of loyal nodes in network
    no_total = 4  #Total number of nodes in network
    result_vect = []  #Final result vector
    result_action = ""  #Final result action

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

    #Displays the current result vector together with the resulting action on the website
    @app.get('/vote/result')
    def get_board():
        global result_vect, result_action
        return template('server/results_template.tpl', result_vect=result_vect, result_action=result_action)

    # NEW BYZANTINE ALGORITHM FUNCTIONS

    #Method called when user presses either 'Attack', 'Retreat' or 'Byzantine' in the web page interface
    #If loyal node, store your own vote in the vote vector, propagate your vote to the other nodes and continue behavior as loyal node (see 'loyal_behaviour()')
    #If byzantine node, continue behaviour as byzantine node (see 'byzantine_behaviour()')
    
    @app.post('/vote/<action>')
    def client_vote_received(action):
        global vote_dict, node_id, byz_node
        try:
            print('The performed action is: ' + action)
            if (int(node_id) not in vote_dict) and (not byz_node):   #A node is only allowed to vote / set byzantine behaviour once
                if action == 'byzantine':
                   byz_node = True
                   byzantine_behavior()
                   return '<h1>Successfully set as Byzantine</h1>'
                if action == 'attack':
                    vote_dict[int(node_id)] = True  #True represents attack
                if action == 'retreat':
                    vote_dict[int(node_id)] = False  #False represents retreat

                print('The current vote vector looks like: ' + str(vote_dict))

                # Propagate action to all other nodes :
                thread = Thread(target=propagate_to_vessels,
                                args=('/propagate/VOTE/', {'action': str(vote_dict[int(node_id)]), 'node_id': str(node_id)}, 'POST'))
                thread.daemon = True
                thread.start()

                loyal_behavior()
                return '<h1>Successfully sent vote</h1>'
        except Exception as e:
            print(e)
        return '<h1>You have already voted!</h1>'

    #Method called when node receives a vote from another node
    #Stores the vote in its vote vector and continues either byzantine or loyal behavior depending on byz_node value (see 'loyal_behaviour()' resp. 'byzantine_behaviour()')
 
    @app.post('/propagate/VOTE/')
    def vote_propagation_received():
        global vote_dict, node_id, byz_node, no_total

        try:
            entry = request.forms.get('action')
            entry = str_to_bool(entry)
            rec_id = int(request.forms.get('node_id'))

            if rec_id not in vote_dict:  #Do not store a vote from a node if you already have a vote from that node
                vote_dict[rec_id] = entry

                print('The current vote vector of size {} is: {}'.format(len(vote_dict), vote_dict))
                byzantine_behavior()
                loyal_behavior()

                return '<h1>Successfully propagated vote</h1>'
            else:
                return '<h1>Node {} had already voted</h1>'.format(rec_id)
        except Exception as e:
            print(e)
        
        return '<h1>Vote propagation failed</h1>'

    #Method for receiving a propagated vote vector (only used by loyal nodes)
    #
    @app.post('/propagate/VOTE/list')
    def list_propagation_received():
        global vote_dict, node_id, byz_node, no_total, no_loyal, vectors, result_vect, result_action

        try:
            entry = request.forms.get('vector')
            node = int(request.forms.get('node_id'))

            vect = entry.split(",")
            vect = [str_to_bool(vote) for vote in vect]
            vectors[node] = vect

            print("LOYAL received vector = {} from node {}".format(vect, node))

            if len(vectors) == no_total and not byz_node:
                result_vect = []
                for i in range(0, no_total):
                    print("")
                    print("Counts votes FOR node " + str(i+1))
                    attack = 0
                    retreat = 0
                    for j in range(1, no_loyal+2):
                        print("Counts votes FROM node {} with vector {}", str(j), vectors[j])
                        if vectors[j][i]:
                            attack += 1
                            print("True added")
                        else:
                            retreat += 1
                            print("False added")
                    if attack > retreat:
                        result_vect.append("Attack")
                    elif retreat > attack:
                        result_vect.append("Retreat")
                    else:
                        result_vect.append("Unknown")
                print("\n\n\n\nNode {} has result vector {}\n\n\n\n".format(node_id, result_vect))

                attack = 0
                retreat = 0

                for k in range(0, len(result_vect)):
                    if result_vect[k] == "Attack":
                        attack += 1
                    if result_vect[k] == "Retreat":
                        retreat += 1
                if attack > (no_loyal*0.5):
                    result_action = "Attack"
                elif retreat > (no_loyal*0.5):
                    result_action = "Retreat"
                else:
                    result_action = "Unknown"

                # Reset
                vote_dict = {}
                vectors = {}
                byz_node = False
            elif byz_node:
                # Reset
                vote_dict = {}
                vectors = {}
                byz_node = False
            else:
                return '<h1>Successfully received vector</h1>'
        except Exception as e:
            print(e)
        return '<h1>Vector propagation failed</h1>'


    #Method for implementing behaviour as byzantine node
    #When votes from all loyal nodes have been received, compute single votes (round 1) to send to the loyal nodes and send them
    #When vote vectors from all loyal nodes have been received, compute vote vectors (round 2) to send to the loyal nodes and send them
    def byzantine_behavior():
        global vote_dict, node_id, byz_node, no_loyal, no_total, vessel_list
        if (len(vote_dict) == no_loyal) and (byz_node == True):
        	#Send votes from round 1 to all loyal nodes
            byz_votes = compute_byzantine_vote_round1(no_loyal,no_total,True)
            loyal_count = 0
            for vessel_id, vessel_ip in vessel_list.items():
                if int(vessel_id) != node_id: # don't propagate to yourself
                    thread = Thread(target=contact_vessel, args=(vessel_ip, '/propagate/VOTE/', {"action": byz_votes[loyal_count], "node_id": node_id}, 'POST'))
                    thread.daemon = True
                    thread.start()
                    loyal_count += 1

            # Send the vote vectors from round 2 to every other loyal process
            byz_vects = compute_byzantine_vote_round2(no_loyal,no_total,True)
            loyal_count = 0
            for vessel_id, vessel_ip in vessel_list.items():
                if int(vessel_id) != node_id: # don't propagate to yourself
                    # Convert vector to string
                    vect = [str(vote) for vote in byz_vects[loyal_count]]
                    vect = ",".join(vect)
                    print("BYZ propagating vector = {}".format(vect))
                    thread = Thread(target=contact_vessel, args=(vessel_ip, '/propagate/VOTE/list', {"vector": vect, 'node_id': node_id}, 'POST'))
                    thread.daemon = True
                    thread.start()
                    loyal_count += 1

    #Method for implementing behaviour as loyal node
    #When the vote vector is full, add it to our own vote vector dictionary ('vectors') and propagate the vote vector to all other nodes
    def loyal_behavior():
        global vote_dict, no_total, byz_node, vectors, node_id
        if len(vote_dict) == no_total and not byz_node:
            # Transform our vote vector to correct format (array)
            vect = []
            for i in range(1, no_total + 1):
                vect.append(vote_dict[i])
            vect = [str(b) for b in vect]
            vect = ",".join(vect)

            #Save vote vector to own vote vector dictionary
            vect_to_add = vect.split(",")
            vect_to_add = [str_to_bool(vote) for vote in vect_to_add]
            vectors[node_id] = vect_to_add

            #Propagate vote vector to other nodes
            print("LOYAL propagating vector = {}".format(vect))
            thread = Thread(target=propagate_to_vessels,
                            args=('/propagate/VOTE/list', {'vector': vect, 'node_id': node_id}, 'POST'))
            thread.daemon = True
            thread.start()

    #Simple methods that the byzantine node calls to decide what to vote.

    #Compute byzantine votes for round 1, by trying to create
    #a split decision.
    #input: 
    #   number of loyal nodes,
    #   number of total nodes,
    #   Decision on a tie: True or False 
    #output:
    #   A list with votes to send to the loyal nodes
    #   in the form [True,False,True,.....]
    def compute_byzantine_vote_round1(no_loyal,no_total,on_tie):

        result_vote = []
        for i in range(0,no_loyal):
            if i%2==0:
                result_vote.append(not on_tie)
            else:
                result_vote.append(on_tie)

        return result_vote

    #Compute byzantine votes for round 2, trying to swing the decision
    #on different directions for different nodes.
    #input: 
    #   number of loyal nodes,
    #   number of total nodes,
    #   Decision on a tie: True or False
    #output:
    #   A list where every element is a the vector that the 
    #   byzantine node will send to every one of the loyal ones
    #   in the form [[True,...],[False,...],...]
    def compute_byzantine_vote_round2(no_loyal,no_total,on_tie):
      
      result_vectors=[]
      for i in range(0,no_loyal):
        if i%2==0:
          result_vectors.append([on_tie]*no_total)
        else:
          result_vectors.append([not on_tie]*no_total)
      return result_vectors
    
    #Method for converting a string value to a boolean value
    def str_to_bool(str):
        return str in ["True", "true", "1"]
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