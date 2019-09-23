import validators
import threading
import traceback
import datetime
import tempfile
import requests
import logging
import shutil
import json
import tqdm
import os
import io
from multiprocessing.pool import ThreadPool
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from .. import PlatformException, entities, repositories, exceptions

logger = logging.getLogger(name=__name__)

NUM_TRIES = 3  # try to upload 3 time before fail on item


class UploadElement:
    def __init__(self, element_type, buffer, remote_filepath, annotations_filepath):
        self.type = element_type
        self.buffer = buffer
        self.remote_filepath = remote_filepath
        self.exists_in_remote = False
        self.checked_in_remote = False
        self.annotations_filepath = annotations_filepath


class Uploader:
    def __init__(self, items_repository):
        assert isinstance(items_repository, repositories.Items)
        self.items_repository = items_repository
        self.__stop_create_existence_dict = False

    def upload(
            self,
            # what to upload
            local_path,
            local_annotations_path=None,
            # upload options
            remote_path=None,
            file_types=None,
            num_workers=32,
            overwrite=False,
    ):
        """
        Upload local file to dataset.
        Local filesystem will remain.
        If "*" at the end of local_path (e.g. "/images/*") items will be uploaded without head directory

        :param overwrite: optional - default = False
        :param local_path: local file or folder to upload
        :param local_annotations_path: path to dataloop format annotations json files.
        :param remote_path: remote path to save.
        :param file_types: list of file type to upload. e.g ['.jpg', '.png']. default is all
        :param num_workers:
        :return: Output (list)
        """
        ###################
        # Default options #
        ###################
        if remote_path is None:
            remote_path = '/'
        if not remote_path.endswith("/"):
            remote_path += "/"
        if file_types is not None and not isinstance(file_types, list):
            msg = '"file_types" should be a list of file extension. e.g [".jpg", ".png"]'
            raise PlatformException(error="400", message=msg)

        ##########################
        # Convert inputs to list #
        ##########################
        local_annotations_path_list = None
        if not isinstance(local_path, list):
            local_path_list = [local_path]
            if local_annotations_path is not None:
                local_annotations_path_list = [local_annotations_path]
        else:
            local_path_list = local_path
            if local_annotations_path is not None:
                assert len(local_annotations_path) == len(local_path_list)
                local_annotations_path_list = local_annotations_path

        if local_annotations_path is None:
            local_annotations_path_list = [None] * len(local_path_list)

        elements = list()
        total_size = 0
        for upload_item_element, upload_annotations_element in zip(local_path_list, local_annotations_path_list):
            if isinstance(upload_item_element, str):
                with_head_folder = True
                if upload_item_element.endswith('*'):
                    with_head_folder = False
                    upload_item_element = os.path.dirname(upload_item_element)

                if os.path.isdir(upload_item_element):
                    # create a list of all the items to upload
                    for root, subdirs, files in os.walk(upload_item_element):
                        for filename in files:
                            _, ext = os.path.splitext(filename)
                            if file_types is None or ext in file_types:
                                filepath = os.path.join(root, filename)  # get full image filepath
                                # extract item's size
                                total_size += os.path.getsize(filepath)
                                # get annotations file
                                if upload_annotations_element is not None:
                                    # change path to annotations
                                    annotations_filepath = filepath.replace(upload_item_element,
                                                                            upload_annotations_element)
                                    # remove image extension
                                    annotations_filepath, _ = os.path.splitext(annotations_filepath)
                                    # add json extension
                                    annotations_filepath += ".json"
                                else:
                                    annotations_filepath = None
                                if with_head_folder:
                                    remote_filepath = remote_path + os.path.relpath(filepath, os.path.dirname(
                                        upload_item_element))
                                else:
                                    remote_filepath = remote_path + os.path.relpath(filepath, upload_item_element)
                                element = UploadElement(element_type='file',
                                                        buffer=filepath,
                                                        remote_filepath=remote_filepath.replace("\\", "/"),
                                                        annotations_filepath=annotations_filepath)
                                elements.append(element)

                # add single file
                elif os.path.isfile(upload_item_element):
                    filepath = upload_item_element
                    # extract item's size
                    total_size += os.path.getsize(filepath)
                    # get annotations file
                    if upload_annotations_element is not None:
                        # change path to annotations
                        annotations_filepath = filepath.replace(upload_item_element, upload_annotations_element)
                        # remove image extension
                        annotations_filepath, _ = os.path.splitext(annotations_filepath)
                        # add json extension
                        annotations_filepath += ".json"
                    else:
                        annotations_filepath = None
                    # append to list
                    remote_filepath = remote_path + os.path.basename(filepath)
                    element = UploadElement(element_type='file',
                                            buffer=filepath,
                                            remote_filepath=remote_filepath,
                                            annotations_filepath=annotations_filepath)
                    elements.append(element)
                elif self.is_url(upload_item_element):
                    # noinspection PyTypeChecker
                    remote_filepath = remote_path + upload_item_element.split('/')[-1]
                    element = UploadElement(element_type='url',
                                            buffer=upload_item_element,
                                            remote_filepath=remote_filepath,
                                            annotations_filepath=upload_annotations_element)
                    elements.append(element)
                else:
                    raise PlatformException("404", "Unknown local path: {}".format(local_path))
            else:
                # binary element
                if not hasattr(upload_item_element, "name"):
                    raise PlatformException(error="400",
                                            message='Must put attribute "name" on buffer (with file name) '
                                                    'when uploading buffers')
                remote_filepath = remote_path + upload_item_element.name
                element = UploadElement(element_type='buffer',
                                        buffer=upload_item_element,
                                        remote_filepath=remote_filepath,
                                        annotations_filepath=upload_annotations_element)
                elements.append(element)
                # get size from binaries
                try:
                    total_size += upload_item_element.__sizeof__()
                except Exception:
                    logger.warning("Cant get binaries size")

        item_remote_filepaths = [element.remote_filepath for element in elements]
        ###################################
        # get remote existence dictionary #
        ###################################
        remote_existence_dict = dict()
        self.__stop_create_existence_dict = False  # used to break and kill the thread
        thread = threading.Thread(
            target=self.__create_existence_dict_worker,
            kwargs={
                "remote_existence_dict": remote_existence_dict,
                "item_remote_filepaths": item_remote_filepaths,
            },
        )
        thread.start()

        num_files = len(elements)
        logger.info("Uploading {} items..".format(num_files))
        output = [0 for _ in range(num_files)]
        status = ["" for _ in range(num_files)]
        success = [False for _ in range(num_files)]
        errors = ["" for _ in range(num_files)]
        pool = ThreadPool(processes=num_workers)
        with tqdm.tqdm(total=num_files) as pbar:
            for i_item in range(num_files):
                element = elements[i_item]
                # check if file exists
                if element.remote_filepath not in remote_existence_dict:
                    # item did not found in dict ( thread still running)  - get existence specifically
                    try:
                        remote_existence_dict[element.remote_filepath] = self.items_repository.get(
                            filepath="{}".format(element.remote_filepath))
                    except exceptions.NotFound:
                        remote_existence_dict[element.remote_filepath] = None

                if remote_existence_dict[element.remote_filepath] is not None:
                    # item exists in platform
                    found_item = remote_existence_dict[element.remote_filepath]
                    if overwrite:
                        # delete and proceed to upload
                        found_item.delete()
                    else:
                        # update, upload annotations and proceed to next item
                        status[i_item] = "exist"
                        output[i_item] = found_item
                        success[i_item] = True

                        # upload annotations if exists
                        if element.annotations_filepath is not None:
                            pool.apply_async(self.__upload_annotations,
                                             kwds={'annotations': element.annotations_filepath,
                                                   'item': found_item})
                        pbar.update()
                        continue
                # upload
                pool.apply_async(self.__upload_single_item_wrapper,
                                 kwds={"i_item": i_item,
                                       "element": element,
                                       "pbar": pbar,
                                       "status": status,
                                       "success": success,
                                       "output": output,
                                       "errors": errors,
                                       },
                                 )
            pool.close()
            pool.join()
        # kill dictionary
        self.__stop_create_existence_dict = True
        thread.join()
        # summary
        n_upload = status.count("upload")
        n_exist = status.count("exist")
        n_error = status.count("error")
        logger.info("Number of files uploaded: {}".format(n_upload))
        logger.info("Number of files exists: {}".format(n_exist))
        logger.info("Number of errors: {}".format(n_error))
        logger.info("Total number of files: {}".format(n_upload + n_exist))

        # log error
        if n_error > 0:
            log_filepath = os.path.join(os.getcwd(),
                                        "log_{}.txt".format(datetime.datetime.now().strftime("%Y%m%d_%H%M%S")))
            errors_list = [errors[i_job] for i_job, suc in enumerate(success) if suc is False]
            with open(log_filepath, "w") as f:
                f.write("\n".join(errors_list))
            logger.warning("Errors in {n_error} files. See {log_filepath} for full log".format(
                n_error=n_error, log_filepath=log_filepath))

        # remove empty cells
        output = [output[i_job] for i_job, suc in enumerate(success) if suc is True]
        if len(output) == 1:
            output = output[0]

        return output

    def __create_existence_dict_worker(self, remote_existence_dict, item_remote_filepaths):
        """

        :param remote_existence_dict: a dictionary that state for each desired remote path if file already exists
        :param item_remote_filepaths: a list of all desired uploaded filepaths
        :return:
        """
        try:
            # get pages of item according to remote filepath

            item_remote_paths = list()
            for filepath in item_remote_filepaths:
                path = os.path.dirname(filepath)
                if path not in item_remote_paths:
                    item_remote_paths.append(path)

            # filters.add(field="type", values="file")
            # add remote paths to check existence
            filters = entities.Filters()
            filters.show_hidden = True
            for remote_path in item_remote_paths:
                if not remote_path.endswith('/'):
                    remote_path += '/'
                filters.add(field='filename', values={'$glob': remote_path + '*'})
            filters.method = 'or'
            pages = self.items_repository.list(filters=filters)

            # join path and filename for all uploads

            for page in pages:
                if self.__stop_create_existence_dict:
                    break
                for item in page:
                    # check in current remote item filename exists in uploaded list
                    if item.filename in item_remote_filepaths:
                        remote_existence_dict[item.filename] = item

            # after listing all platform file make sure everything in dictionary
            for item_remote_filepath in item_remote_filepaths:
                if item_remote_filepath not in remote_existence_dict:
                    remote_existence_dict[item_remote_filepath] = None

        except Exception:
            logger.error('{}\nCant create existence dictionary when uploading'.format(traceback.format_exc()))

    def __upload_single_item(self,
                             filepath,
                             annotations,
                             remote_path,
                             uploaded_filename,
                             last_try
                             ):
        """
        Upload an item to dataset

        :param annotations: platform format annotations file to add to the new item
        :param filepath: local filepath of the item
        :param remote_path: remote directory of filepath to upload
        :param uploaded_filename: optional - remote filename
        :param last_try: print log error only if last try
        :return: Item object
        """
        need_close = False
        if isinstance(filepath, str):
            # upload local file
            if not os.path.isfile(filepath):
                raise PlatformException(error="404", message="Filepath doesnt exists. file: {}".format(filepath))
            if uploaded_filename is None:
                uploaded_filename = os.path.basename(filepath)
            if os.path.isfile(filepath):
                item_type = 'file'
            else:
                item_type = 'dir'
            item_size = os.stat(filepath).st_size
            to_upload = open(filepath, 'rb')
            need_close = True

        else:
            # upload from buffer
            if isinstance(filepath, bytes):
                to_upload = io.BytesIO(filepath)
            elif isinstance(filepath, io.BytesIO):
                to_upload = filepath
            elif isinstance(filepath, io.BufferedReader):
                to_upload = filepath
            elif isinstance(filepath, io.TextIOWrapper):
                to_upload = filepath
            else:
                raise PlatformException("400", "unknown file type")

            if uploaded_filename is None:
                if hasattr(filepath, "name"):
                    uploaded_filename = filepath.name
                else:
                    raise PlatformException(error="400",
                                            message="Must have filename when uploading bytes array (uploaded_filename)")

            item_size = to_upload.seek(0, 2)
            to_upload.seek(0)
            item_type = 'file'
        remote_url = "/datasets/{}/items".format(self.items_repository.dataset.id)
        try:
            result, response = self.items_repository._client_api.upload_from_local(to_upload=to_upload,
                                                                                   item_size=item_size,
                                                                                   item_type=item_type,
                                                                                   remote_url=remote_url,
                                                                                   uploaded_filename=uploaded_filename,
                                                                                   remote_path=remote_path,
                                                                                   log_error=last_try)
        except:
            raise
        finally:
            if need_close:
                to_upload.close()

        if result:
            item = self.items_repository.items_entity.from_json(client_api=self.items_repository._client_api,
                                                                _json=response.json(),
                                                                dataset=self.items_repository.dataset)
            if annotations is not None:
                try:
                    self.__upload_annotations(annotations=annotations, item=item)
                except Exception:
                    logger.error(traceback.format_exc())
        else:
            raise PlatformException(response)
        return item

    def __upload_single_item_wrapper(self, i_item, element, pbar, status, success, output, errors, ):
        assert isinstance(element, UploadElement)
        item = False
        err = None
        trace = None
        saved_locally = False
        temp_dir = None
        remote_folder, remote_filename = os.path.split(element.remote_filepath)
        for i_try in range(NUM_TRIES):
            try:
                logger.debug("Upload item: {path}. Try {i}/{n}. Starting..".format(path=remote_filename,
                                                                                   i=i_try + 1,
                                                                                   n=NUM_TRIES))
                if element.type == 'url':
                    saved_locally, element.buffer, temp_dir = self.url_to_data(element.buffer)
                item = self.__upload_single_item(filepath=element.buffer,
                                                 annotations=element.annotations_filepath,
                                                 remote_path=remote_folder,
                                                 uploaded_filename=remote_filename,
                                                 last_try=(i_try + 1) == NUM_TRIES)
                logger.debug("Upload item: {path}. Try {i}/{n}. Success. Item id: {id}".format(path=remote_filename,
                                                                                               i=i_try + 1,
                                                                                               n=NUM_TRIES,
                                                                                               id=item.id))
                if isinstance(item, entities.Item):
                    break
            except Exception as e:
                logger.debug("Upload item: {path}. Try {i}/{n}. Fail.".format(path=remote_filename,
                                                                              i=i_try + 1,
                                                                              n=NUM_TRIES))
                err = e
                trace = traceback.format_exc()
            finally:
                if saved_locally and os.path.isdir(temp_dir):
                    shutil.rmtree(temp_dir)
        if item:
            status[i_item] = "upload"
            output[i_item] = item
            success[i_item] = True
        else:
            status[i_item] = "error"
            output[i_item] = remote_folder + remote_filename
            success[i_item] = False
            errors[i_item] = "{}\n{}".format(err, trace)
        pbar.update()

    @staticmethod
    def __upload_annotations(annotations, item):
        """
        Upload annotations from file
        :param annotations: file path
        :param item: item
        :return:
        """
        if isinstance(annotations, str) and os.path.isfile(annotations):
            with open(annotations, "r") as f:
                data = json.load(f)
            if "annotations" in data:
                annotations = data["annotations"]
            elif isinstance(data, list):
                annotations = data
            else:
                raise PlatformException(
                    error="400",
                    message='MISSING "annotations" in annotations file, cant upload. item_id: {}, '
                            "annotations_filepath: {}".format(item.id, annotations),
                )
            item.annotations.upload(annotations=annotations)

    @staticmethod
    def url_to_data(url):
        chunk_size = 8192
        max_size = 30000000
        temp_dir = None

        # This will download the binaries from the URL user provided
        prepared_request = requests.Request(method='GET', url=url).prepare()
        with requests.Session() as s:
            retry = Retry(
                total=3,
                read=3,
                connect=3,
                backoff_factor=0.3,
            )
            adapter = HTTPAdapter(max_retries=retry)
            s.mount('http://', adapter)
            s.mount('https://', adapter)
            response = s.send(request=prepared_request, stream=True)

        total_length = response.headers.get("content-length")
        save_locally = int(total_length) > max_size

        if save_locally:
            # save to file
            temp_dir = tempfile.mkdtemp()
            temp_path = os.path.join(temp_dir, url.split('/')[-1])
            with open(temp_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:  # filter out keep-alive new chunks
                        f.write(chunk)
            # save to output variable
            data = temp_path
        else:
            # save as byte stream
            data = io.BytesIO()
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:  # filter out keep-alive new chunks
                    data.write(chunk)
            # go back to the beginning of the stream
            data.seek(0)
            data.name = url.split('/')[-1]

        return save_locally, data, temp_dir

    @staticmethod
    def is_url(url):
        try:
            return validators.url(url)
        except Exception:
            return False
