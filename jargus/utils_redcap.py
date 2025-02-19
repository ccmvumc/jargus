import redcap
import os
import logging


def download_named_file(project, record_id, field_id, outdir, event_id=None, repeat_id=None):
    # Get the file contents from REDCap
    try:
        (cont, hdr) = project.export_file(
            record=record_id,
            field=field_id,
            event=event_id,
            repeat_instance=repeat_id)

        if cont == '':
            raise redcap.RedcapError
    except redcap.RedcapError as err:
        logging.error(f'downloading file:{err}')
        return None

    # Save contents to local file
    filename = os.path.join(outdir, hdr['name'])
    try:
        with open(filename, 'wb') as f:
            f.write(cont)

        return filename
    except FileNotFoundError as err:
        logging.error(f'file not found:{filename}:{err}')
        return None


def download_file(project, record_id, field_id, filename, event_id=None, repeat_id=None):
    # Get the file contents from REDCap
    try:
        (cont, hdr) = project.export_file(
            record=record_id,
            field=field_id,
            event=event_id,
            repeat_instance=repeat_id)

        if cont == '':
            raise redcap.RedcapError
    except redcap.RedcapError as err:
        logging.error(f'downloading file:{err}')
        return None

    # Save contents to local file
    try:
        with open(filename, 'wb') as f:
            f.write(cont)

        return filename
    except FileNotFoundError as err:
        logging.error(f'file not found:{filename}:{err}')
        return None


def upload_file(project, record_id, field_id, filename, event_id=None, repeat_id=None):
    with open(filename, 'rb') as f:
        project.import_file(
            record=record_id,
            field=field_id,
            file_name=os.path.basename(filename),
            event=event_id,
            repeat_instance=repeat_id,
            file_object=f)


def get_redcap(project_id, key_file=None, api_url=None, api_key=None):
    # Check for overrides in environment vars
    api_url = os.environ.get('REDCAP_API_URL', api_url)
    key_file = os.environ.get('REDCAP_API_KEYFILE', key_file)

    if not api_url:
        api_url = 'https://redcap.vumc.org/api/'

    if not api_key:
        # key not specified so we read it from file

        if not key_file:
            # no key file specified so we use the default location
            key_file = os.path.join(os.path.expanduser('~'), '.redcap.txt')

        # Load from the key file
        api_key = get_projectkey(project_id, key_file)

    if not api_key:
        raise Exception('api key not found in file or arguments')

    return redcap.Project(api_url, api_key)


def get_projectkey(project_id, key_file):
    # Load the dictionary
    d = {}
    with open(key_file) as f:
        for line in f:
            if line == '':
                continue

            try:
                (i, k, n) = line.strip().split(',')
                d[i] = k
            except:
                pass

    # Return the key id for given project id
    return d.get(project_id, None)


def get_projectid(projectname, keyfile):
    # Load the dictionary mapping name to id
    d = {}
    with open(keyfile) as f:
        for line in f:
            if line == '':
                continue
            try:
                (i, k, n) = line.strip().split(',')
                # Map name to id
                d[n] = i
            except:
                pass
    # Return the project id for given project name
    return d.get(projectname, None)


def get_jargus_redcap():
    api_url = 'https://redcap.vumc.org/api/'
    keyfile = os.path.join(os.path.expanduser('~'), '.redcap.txt')

    # Check for overrides in environment vars
    api_url = os.environ.get('REDCAP_API_URL', api_url)
    keyfile = os.environ.get('REDCAP_API_KEYFILE', keyfile)

    project_id = get_projectid('jargus', keyfile)
    api_key = get_projectkey(project_id, keyfile)

    return redcap.Project(api_url, api_key)


def match_repeat(rc, record_id, repeat_name, match_field, match_value):
    # Load potential matches
    records = rc.export_records(records=[record_id])

    # Find records with matching vaue
    matches = [x for x in records if x[match_field] == match_value]

    # Return ids of matches
    return [x['redcap_repeat_instance'] for x in matches]


def field2events(project, field_id):
    _form = [x['form_name'] for x in project.metadata if x['field_name'] == field_id][0]
    return [x['unique_event_name'] for x in project.export_instrument_event_mappings() if x['form'] == _form]
