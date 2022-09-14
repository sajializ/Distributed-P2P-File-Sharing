import sys
import json
import socket
import selectors
import select
import types
from multiprocessing import Process
from finder import Finder
import time
from progress.bar import Bar


class Node:
    PORT = 65432  # Port to listen on (non-privileged ports are > 1023)
    SEND_PORT = 12345
    BUFSIZE = 1024
    TTL = 5

    def __init__(self) -> None:
        self.host_addr = sys.argv[1]
        self.server_addr = ""
        self.server_addr = sys.argv[2]
        if sys.argv[3] == "True":
            self.is_blutooth = True
        else:
            self.is_blutooth = False
        
        self.topology = {self.host_addr: []}
        Finder.hash_files()
        
    @staticmethod
    def handle_input(input) -> list:
        try:
            input_list = list(input.strip().lower().split())
            if input_list[0] == "request":
                return Node.generate_message(["command", "filename"], input_list)
            elif input_list[0] == "connect":
                return Node.generate_message(["command", "address"], input_list)
            elif input_list[0] == "request_hash":
                return Node.generate_message(["command", "filename"], input_list)
        except:
            pass

    @staticmethod
    def show_menu(options):
        index = 1
        for d in options:
            print(f"{index} -- Name: {d['name'].split('/')[-1]} -- Size: {d['size']} (B) -- Ratio: {d['ratio']}")
            index += 1
        print(f"{index} -- Exit")

    def handle_command(self, command_list) -> None:        
        command = command_list['command']
        if command == "quit" or command == "exit":
            sys.exit()
        elif command == "request":
            if len(self.topology[self.host_addr]) == 0:
                print("YOU ARE DISCONNECTED FROM NETWORK, USE connect")
                return

            result = self.request_file(command_list, "download", "request")
            if not result:
                print("DONWLOAD FAILED, RETRYING")
                self.request_file(command_list, "download", "request")
                
        elif command == "request_hash":
            if len(self.topology[self.host_addr]) == 0:
                print("YOU ARE DISCONNECTED FROM NETWORK, USE connect")
                return

            result = self.request_file(command_list, "download", "request_hash")
            if not result:
                print("DONWLOAD FAILED, RETRYING")
                self.request_file(command_list, "download", "request_hash")
        
        elif command == "connect":
            try:
                self.connect(command_list["address"])
            except Exception as e:
                print("CANNOT CONNECT TO THIS ADDRESS")
        else:
            print("UKNOWN COMMAND")
    
    def request_file(self, command_list, command_type, request_type):
            down_nodes = []
            
            for neighbor in self.topology[self.host_addr]:
                try:
                    neighbor_socket, data = Node.query_file(neighbor, command_list["filename"], [self.host_addr], Node.TTL, request_type)
                    if neighbor_socket != None:
                        Node.show_menu(data["data"])

                        option = int(input("Choose your option: "))
                        while not (option < len(data["data"]) + 2 and option > 0):
                            print("Please try again")
                            option = int(input("Choose your option: "))
                        
                        if option == len(data["data"]) + 1:
                            return False

                        ip = data["ips"].pop()
                        filename = data["data"][option - 1]["name"]
                        size = data["data"][option - 1]["size"]
                        
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as data_socket:
                            data_socket.connect((ip, Node.PORT))
                            Node.send(data_socket, Node.generate_message(["command", "data", "ips"], [command_type, data["data"][option - 1], data["ips"]]))
                            return Node.receive_file(filename.split('/')[-1], size, data_socket)
                            
                except Exception as e:
                    down_nodes.append(neighbor)
            
            for node in down_nodes:
                self.topology[self.host_addr].remove(node)
            
            if len(self.topology[self.host_addr]) == 0:
                print("YOU ARE DISCONNECTED FROM NETWORK, USE connect")
            else:
                print("NO FILE FOUND")

    def handle_peer_command(self, command_list, server_conn, server_addr):
        command = command_list['command']
        
        if command == "connect":
            response = self.handle_connect(command_list["address"])
            Node.send(server_conn, Node.generate_message(["status", "data"], ["okay", response]))
        
        elif command == "request":
            if int(command_list["ttl"]) < 1:
                Node.send(server_conn, Node.generate_message(["status"], ["not_okay"]))
                return

            results = {"data": Finder.get_similarity_matching(command_list["filename"])}
            if len(results["data"]):
                results["ips"] = [self.host_addr]
                Node.send(server_conn, Node.generate_message(["status", "data", "ips"], ["okay", results["data"], results["ips"]]))
            else:
                down_nodes = []
                if len(self.topology[self.host_addr]) == 0:
                    Node.send(server_conn, Node.generate_message(["status"], ["not_okay"]))
                    print("YOU ARE DISCONNECTED FROM NETWORK, USE connect")
                    return
                for neighbor in self.topology[self.host_addr]:
                    if neighbor != server_addr[0]:
                        try:
                            neighbor_socket, data = Node.query_file(neighbor, command_list["filename"], command_list["ips"], int(command_list["ttl"]) - 1, "request")
                            if neighbor_socket != None:
                                data["ips"].append(self.host_addr)
                                Node.send(server_conn, Node.generate_message(["status", "data", "ips"], ["okay", data["data"], data["ips"]]))
                                return
                        except Exception as e:
                            down_nodes.append(neighbor)

                for node in down_nodes:
                    self.topology[self.host_addr].remove(node)

                if len(self.topology[self.host_addr]) == 0:
                    print("YOU ARE DISCONNECTED FROM NETWORK, USE connect")
                else:
                    print("NO FILE FOUND")
                Node.send(server_conn, Node.generate_message(["status"], ["not_okay"]))

        elif command == "download":
            results = {"data": Finder.get_path(command_list["data"]["name"].split("/")[-1])}
            if len(results["data"]):
                results["ips"] = [self.host_addr]
                send_process = Process(target=Node.send_file, args=(server_conn, command_list["data"]["name"],))
                send_process.start()
            else:
                for neighbor in self.topology[self.host_addr]:
                    if neighbor != server_addr[0]:
                        ip = command_list["ips"].pop()
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
                            
                            client_socket.connect((ip, Node.PORT))
                            send_process = Process(target=Node.route_file, args=(server_conn, client_socket, command_list,))
                            send_process.start()
                        return
                Node.send(server_conn, Node.generate_message(["status"], ["not_okay"]))

        elif command == "request_hash":
            if int(command_list["ttl"]) < 1:
                Node.send(server_conn, Node.generate_message(["status"], ["not_okay"]))
                return
            results = {"data": Finder.get_hash_path(command_list["filename"])}
            if len(results["data"]):
                results["ips"] = [self.host_addr]
                Node.send(server_conn, Node.generate_message(["status", "data", "ips"], ["okay", results["data"], results["ips"]]))
            else:
                down_nodes = []
                if len(self.topology[self.host_addr]) == 0:
                    Node.send(server_conn, Node.generate_message(["status"], ["not_okay"]))
                    print("YOU ARE DISCONNECTED FROM NETWORK, USE connect")
                    return
                for neighbor in self.topology[self.host_addr]:
                    if neighbor != server_addr[0]:
                        try:
                            neighbor_socket, data = Node.query_file(neighbor, command_list["filename"], command_list["ips"], int(command_list["ttl"]) - 1, "request_hash")
                            if neighbor_socket != None:
                                data["ips"].append(self.host_addr)
                                Node.send(server_conn, Node.generate_message(["status", "data", "ips"], ["okay", data["data"], data["ips"]]))
                                return
                        except Exception as e:
                            down_nodes.append(neighbor)

                for node in down_nodes:
                    self.topology[self.host_addr].remove(node)

                if len(self.topology[self.host_addr]) == 0:
                    print("YOU ARE DISCONNECTED FROM NETWORK, USE connect")
                else:
                    print("NO FILE FOUND")
                Node.send(server_conn, Node.generate_message(["status"], ["not_okay"]))

    @staticmethod
    def query_file(address, filename, ips, ttl, request_type):
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((address, Node.PORT))
        Node.send(client_socket, Node.generate_message(["command", "filename", "ips", "ttl"], [request_type, filename, ips, ttl]))
        data = Node.recv(client_socket)
        if data["status"] == "okay":
            return client_socket, data
        return None, None

    @staticmethod
    def route_file(source, destination, data):
            Node.send(destination, data)
            received = 0
            prev, now = 0, 0
            with Bar(f"Routing {data['data']['name']}...", fill='#', suffix='%(percent)d%%') as bar:
                while received < data["data"]["size"]:
                    chunk = destination.recv(Node.BUFSIZE)
                    source.send(chunk)
                    received += len(chunk)

                    now = int(received * 100 / data["data"]["size"])
                    for _ in range(prev, now):
                        bar.next()
                    prev = now

    @staticmethod
    def send_file(server_conn, filename):
            print(filename)
            with open(filename, "rb") as binary_file:
                while (chunk := binary_file.read(Node.BUFSIZE)):
                    while True:
                        try:
                            server_conn.send(chunk)
                            break
                        except:
                            pass

            print("Sent ", filename, " successfully")

    @staticmethod
    def send_hash_file(server_conn, filename):
            with open(filename, "rb") as binary_file:
                while (chunk := binary_file.read(Node.BUFSIZE)):
                    server_conn.send(chunk)

            print("Sent ", filename, " successfully")


    def handle_connect(self, address):
        if address not in self.topology[self.host_addr]:
            self.topology[self.host_addr].append(address)
        self.topology.update({
            self.host_addr: self.topology[self.host_addr]
        })
        self.topology[address] = [self.host_addr]
        return self.topology

    def connect(self, address) -> None:
        if address != "":
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
                client_socket.connect((address, Node.PORT))
                Node.send(client_socket, Node.generate_message(["command", "address"], ["connect", self.host_addr]))
                self.topology.update(Node.recv(client_socket)["data"])
                print(self.topology)
    
    def listen(self):
        if self.is_blutooth:
            server_socket = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        else:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        server_socket.bind((self.host_addr, Node.PORT))
        server_socket.listen()
        server_socket.setblocking(False)
        while True:
            input_ready, output_ready, except_ready = select.select([server_socket, sys.stdin], [], [])
            for event in input_ready:
                if event == server_socket:
                    server_conn, server_addr = server_socket.accept()
                    while True:
                            try:
                                data = Node.recv(server_conn)
                                break
                            except:
                                pass
                    response = self.handle_peer_command(data, server_conn, server_addr)
               
                else:
                    input_list = Node.handle_input(input())
                    node.handle_command(input_list)
                

    @staticmethod
    def generate_message(properties, values):
        message = {}
        for property, value in zip(properties, values):
            message[property] = value
        return message

    def client(self):
        if self.server_addr != "":
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
                client_socket.connect((self.server_addr, Node.PORT))
                Node.send(client_socket, Node.generate_message(["command", "address"], ["connect", self.host_addr]))
                self.topology.update(Node.recv(client_socket)["data"])

    @staticmethod
    def receive_file(filename, size, connection):
        connection.settimeout(5.0)
        with open(filename, "wb") as binary_file:
            received = 0
            prev, now = 0, 0
            with  Bar(f"Downloading {filename}...", fill='#', suffix='%(percent)d%%') as bar:
                while received < size:
                    chunk = connection.recv(Node.BUFSIZE)
                    binary_file.write(chunk)
                    received += len(chunk)

                    if len(chunk) == 0:
                        return False

                    now = int(received * 100 / size)
                    for _ in range(prev, now):
                        bar.next()
                    prev = now

        return True

    #depricated
    @staticmethod
    def send_request(command, address, filename):
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((address, Node.PORT))
        Node.send(client_socket, Node.generate_message(["command", "filename"], [command, filename]))
        data = Node.recv(client_socket)
        if data["status"] == "okay":
            filename = data["data"][0]["name"]
            size = data["data"][0]["size"]
            Node.send(client_socket, Node.generate_message(["command", "filename"], ["download", filename]))
            Node.receive_file(filename.split('/')[-1], size, client_socket)
        client_socket.close()

    @staticmethod
    def send(conn, data) -> None:    
        conn.send(json.dumps(data).encode("utf-8"))

    @staticmethod
    def recv(conn) -> object:
        data = conn.recv(Node.BUFSIZE).decode("utf-8")
        return json.loads(data)

if __name__ == "__main__":
    node = Node()
    node.connect(node.server_addr)

    node.listen()
        
        
