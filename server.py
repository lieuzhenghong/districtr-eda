import os.path
import flask
from flask import Flask
from flask import request
from flask_cors import CORS
import json
import geopandas as gpd
import gerrychain
import networkx as nx

app = Flask(__name__)
CORS(app)

import os.path
dir_path = os.path.dirname(os.path.realpath(__file__))

state_shapefile_paths = {
    "iowa": f'{dir_path}/shapefiles/IA_counties/IA_counties.shp',
    "texas": f'{dir_path}/shapefiles/TX_vtds/TX_vtds.shp',
}

def form_assignment_from_state_graph(districtr_assignment, node_to_id, state_graph):
    '''
    Converts a Districtr graph assignment (which node belongs to which district)
    into an assignment that works with Gerrychain
    Requires a Districtr graph assignment, 
    a mapping of Districtr nodes to Gerrychain nodes,
    and the appropriate state dual graph.
    Assigns all unassigned nodes to a district -1.
    Returns an assignment of each node in the state graph to to a district.
    '''
    assignment = {}
    for node in state_graph:
        node_id = node_to_id[node]
        if node_id in districtr_assignment:
            if isinstance(districtr_assignment[node_id], list):
                assert(len(districtr_assignment[node_id]) == 1)
                # print(districtr_assignment[node_id][0])
                assignment[node] = districtr_assignment[node_id][0]
            else:
                assignment[node] = districtr_assignment[node_id]
        else:
            # We assign to -1
            assignment[node] = -1
    return assignment

@app.route('/', methods=['POST'])
# Takes a Districtr JSON and returns whether or not it's contiguous and number of cut edges.
def plan_metrics():
    plan = request.get_json()
    
    state = plan['placeId'] # get the state of the Districtr plan
    # Check if we already have a dual graph of the state
    dual_graph_path = f"{dir_path}/dual_graphs/mggg-dual-graphs/{state}.json"
    print(dual_graph_path)

    if os.path.isfile(dual_graph_path):
        state_graph = gerrychain.Graph.from_json(dual_graph_path)
    else:
        print("No dual graph found, generating our own.")
        try:
            # TODO timeit this --- how long does it take to load into memory?
            state_shapefile_path = state_shapefile_paths[state]
            state_graph = gerrychain.Graph.from_file(state_shapefile_path)
            state_graph.to_json(f'{dir_path}/dual_graphs/{state}_dual.json')
            print("Dual graph generated!")
        except GeometryError as e:
            print(e)
        except ValueError:
            response = flask.jsonify({'error': "Don't have either dual graph or shapefile for this state"})
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
    # TODO timeit this --- how long does it take?
    assignment = form_assignment_from_state_graph(districtr_assignment, node_to_id, state_graph)

    # TODO timeit this --- how long does it take?
    partition = gerrychain.Partition(state_graph, assignment, None)

    # Now that we have the partition, calculate all the different metrics

    # Calculate cut edges
    cut_edges = (partition['cut_edges'])

    # Split districts
    # TODO timeit this --- how long does it take?
    split_districts = []
    for part in gerrychain.constraints.contiguity.affected_parts(partition):
        if part != -1:
            part_contiguous = nx.is_connected(partition.subgraphs[part])
            if not part_contiguous:
                split_districts.append(part)

    # Contiguity
    contiguity = (len(split_districts) == 0)

    response = flask.jsonify({'cut_edges': str(cut_edges), 'contiguity': contiguity, 'split': split_districts})
    return response