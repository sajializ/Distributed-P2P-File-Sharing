import os
import glob
import hashlib
from difflib import SequenceMatcher

class Finder:
    PATH = os.path.expanduser(os.path.dirname(os.path.abspath(__file__)) + "/files/")
    MD5 = hashlib.md5()
    BUFSIZE = 1024
    HASHTABLE = dict()

    @staticmethod
    def get_path(filename):
        result = []
        for file_path in glob.glob(Finder.PATH+f"{filename}*"): #To find files in a directory with a partial string match
                file_size = os.path.getsize(file_path)
                result.append({"name": file_path, "size": file_size})
        
        return result
    
    @staticmethod
    def get_similarity_matching_ratio(a, b):
        return SequenceMatcher(None, a, b).ratio()
    
    @staticmethod
    def get_similarity_matching(filename):
        files = Finder.get_path("")
        for file in files:
            file["ratio"] = Finder.get_similarity_matching_ratio(filename, file["name"])
        files.sort(key=lambda x: x["ratio"], reverse=True)
        return files
    
    @staticmethod
    def get_hash_path(hash):
        if hash not in Finder.HASHTABLE:
            return []
        return Finder.HASHTABLE[hash]

    @staticmethod
    def get_file_hash(file_path, root, filename):
        with open(file_path, 'rb') as file:
            while True:
                data = file.read(Finder.BUFSIZE)
                if not data:
                    break
                Finder.MD5.update(data)
            file_path = os.path.join(root, filename)
            file_size = os.path.getsize(file_path)
            return [{"name": file_path, "size": file_size}]

    @staticmethod
    def hash_files():
        for root, dirs, files in os.walk(Finder.PATH):
            for filename in files:
                file_path = os.path.join(root, filename)
                file_hash = Finder.get_file_hash(file_path, root, filename)
                Finder.HASHTABLE[Finder.MD5.hexdigest()] = file_hash
                Finder.MD5 = hashlib.md5()
                
