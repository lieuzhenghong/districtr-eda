import os.path
import flask
from flask import Flask
from flask import request
from flask_cors import CORS
import json
import geopandas as gpd
import gerrychain

app = Flask(__name__)
CORS(app)

import os.path
dir_path = os.path.dirname(os.path.realpath(__file__))

state_shapefile_paths = {
    "iowa": f'{dir_path}/shapefiles/IA_counties/IA_counties.shp',
    "texas": f'{dir_path}/shapefiles/TN_vtds/TN_vtds.shp',
}

@app.route('/', methods=['POST'])
# Takes a Districtr JSON and returns whether or not it's contiguous and number of cut edges.
def plan_metrics():
    #print("Request received")
    #print(request)
    plan = request.get_json()
    #print(plan)
    
    state = plan['placeId'] # get the state of the Districtr plan
    # Check if we already have a dual graph of the state
    dual_graph_path = f"{dir_path}/dual_graphs/{state}_dual.json"
    print(dual_graph_path)

    if os.path.isfile(dual_graph_path):
        state_graph = gerrychain.Graph.from_json(dual_graph_path)
    else:
        print("No dual graph found, generating our own.")
        try:
            state_shapefile_path = state_shapefile_paths[state]
            state_graph = gerrychain.Graph.from_file(state_shapefile_path)
            state_graph.to_json(f'{dir_path}/dual_graphs/{state}_dual.json')
        except ValueError:
            response = flask.jsonify({'error': "Don't have either dual graph or shapefile for this state"})
            #response.headers.add('Access-Control-Allow-Origin', '*')
            return response

    # OK, so now we are guaranteed to have the state graph.
    # Form the partition with the JSON path (requires state graph)
    # This is taken from the Districtr function from_districtr_file
    # https://gerrychain.readthedocs.io/en/latest/_modules/gerrychain/partition/partition.html
    id_column_key = plan["idColumn"]["key"]
    districtr_assignment = plan["assignment"]
    print(districtr_assignment)

    try:
        node_to_id = {node: str(state_graph.nodes[node][id_column_key]) for node in state_graph}
    except KeyError:
        response = flask.jsonify({'error':
            "The provided graph is missing the {} column, which is "
            "needed to match the Districtr assignment to the nodes of the graph."
        })
        return response

    # If everything checks out, form a Partition
    print(districtr_assignment)

    assignment = {}
    for node in state_graph:
        if node_to_id[node] in districtr_assignment:
            if isinstance(districtr_assignment[node_to_id[node]], list):
                assert(len(districtr_assignment[node_to_id[node]]) == 1)
                print(districtr_assignment[node_to_id[node][0]])
                assignment[node] = districtr_assignment[node_to_id[node][0]]
            else:
                assignment[node] = districtr_assignment[node_to_id[node]]
        else:
            # We assign to -1
            assignment[node] = -1

    print(assignment)

    # assignment = {node: districtr_assignment[node_to_id[node]] for node in state_graph}
    partition = gerrychain.Partition(state_graph, assignment, None)

    # Now that we have the partition, calculate all the different metrics
    cut_edges = (partition['cut_edges'])
    contiguity = (gerrychain.constraints.contiguity.contiguous(partition))


    response = flask.jsonify({'cut_edges': str(cut_edges), 'contiguity': contiguity})
    #response.headers.add('Access-Control-Allow-Origin', '*')
    return response
