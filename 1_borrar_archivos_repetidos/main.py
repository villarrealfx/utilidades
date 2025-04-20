import os
import hashlib

def hash_file(filename):
    h = hashlib.md5()
    with open(filename, 'rb') as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def find_duplicates(folder):
    hashes = {}
    duplicates = []

    for dirpath, _, filenames in os.walk(folder):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            file_hash = hash_file(filepath)

            if file_hash in hashes:
                duplicates.append((hashes[file_hash], filepath))
                print(f"Duplicate found: {hashes[file_hash]} and {filepath}")
                delete = input(f"Do you want to delete {filepath}? (y/n): ").strip().lower()
                if delete == 'y':
                    os.remove(filepath)
                    print(f"Deleted {filepath}")
                else:
                    print(f"Keeping file {filepath}")
            else:
                hashes[file_hash] = filepath

    return duplicates

if __name__ == "__main__":
    folder = input("Enter the folder path to search for duplicates: ").strip()
    if os.path.isdir(folder):
        find_duplicates(folder)
    else:
        print("Invalid folder path.")
