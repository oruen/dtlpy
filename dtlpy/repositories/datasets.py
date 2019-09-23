"""
Datasets Repository
"""

import logging
from urllib.parse import urlencode
from .. import entities, repositories, utilities, PlatformException

logger = logging.getLogger(name=__name__)


class Datasets:
    """
    Datasets repository
    """

    def __init__(self, client_api, project=None):
        self._client_api = client_api
        self._project = project

    @property
    def project(self):
        if self._project is None:
            raise PlatformException(
                error='400',
                message='Cannot perform action WITHOUT Project entity in Datasets repository. Please set a project')
        assert isinstance(self._project, entities.Project)
        return self._project

    @project.setter
    def project(self, project):
        if not isinstance(project, entities.Project):
            raise ValueError('Must input a valid Project entity')
        self._project = project

    def __get_by_id(self, dataset_id):
        success, response = self._client_api.gen_request(req_type='get',
                                                         path='/datasets/{}'.format(dataset_id))
        if success:
            dataset = entities.Dataset.from_json(client_api=self._client_api,
                                                 _json=response.json(),
                                                 project=self._project)
        else:
            raise PlatformException(response)
        return dataset

    def __get_by_identifier(self, identifier):
        datasets = self.list()
        datasets_by_name = [dataset for dataset in datasets if dataset.name == identifier]
        if len(datasets_by_name) == 1:
            return datasets_by_name[0]
        elif len(datasets_by_name) > 1:
            raise Exception('Multiple datasets with this name exist')

        datasets_by_partial_id = [dataset for dataset in datasets if dataset.id.startswith(identifier)]
        if len(datasets_by_partial_id) == 1:
            return datasets_by_partial_id[0]
        elif len(datasets_by_partial_id) > 1:
            raise Exception("Multiple datasets whose id begins with {} exist".format(identifier))

        raise Exception("Dataset not found")

    def open_in_web(self, dataset_name=None, dataset_id=None, dataset=None):
        import webbrowser
        if self._client_api.environment == 'https://gate.dataloop.ai/api/v1':
            head = 'https://console.dataloop.ai'
        elif self._client_api.environment == 'https://dev-gate.dataloop.ai/api/v1':
            head = 'https://dev-con.dataloop.ai'
        else:
            raise PlatformException('400', 'Unknown environment')
        if dataset is None:
            dataset = self.get(dataset_name=dataset_name, dataset_id=dataset_id)
        dataset_url = head + '/projects/{}/datasets/{}'.format(dataset.project.id, dataset.id)
        webbrowser.open(url=dataset_url, new=2, autoraise=True)

    def checkout(self, identifier):
        if self._project is not None:
            self.project.checkout()
        else:
            project_id = self._client_api.state_io.get('project')
            if project_id is None:
                raise Exception("Please checkout a valid project before trying to checkout a dataset")
            projects = repositories.Projects(client_api=self._client_api)
            self.project = projects.get(project_id=project_id)
        dataset = self.__get_by_identifier(identifier)
        self._client_api.state_io.put('dataset', dataset.id)
        logger.info('Checked out to dataset {}'.format(dataset.name))

    def list(self):
        """
        List all datasets.

        :return: List of datasets
        """
        query_string = urlencode({'name': '', 'creator': '', 'projects': self.project.id}, doseq=True)
        success, response = self._client_api.gen_request(req_type='get',
                                                         path='/datasets?{}'.format(query_string))
        if success:
            datasets = utilities.List([entities.Dataset.from_json(client_api=self._client_api,
                                                                  _json=_json,
                                                                  project=self.project)
                                       for _json in response.json()])
        else:
            raise PlatformException(response)
        return datasets

    def get(self, dataset_name=None, dataset_id=None):
        """
        Get dataset by name or id

        :param dataset_name: optional - search by name
        :param dataset_id: optional - search by id
        :return: Dataset object
        """
        if dataset_id is not None:
            dataset = self.__get_by_id(dataset_id)
        elif dataset_name is not None:
            datasets = self.list()
            dataset = [dataset for dataset in datasets if dataset.name == dataset_name]
            if not dataset:
                # empty list
                raise PlatformException('404', 'Dataset not found. Name: {}'.format(dataset_name))
                # dataset = None
            elif len(dataset) > 1:
                # more than one dataset
                logger.warning('More than one dataset with same name. Please "get" by id')
                raise PlatformException('400', 'More than one dataset with same name.')
            else:
                dataset = dataset[0]
        else:
            # get from state cookie
            state_dataset_id = self._client_api.state_io.get('dataset')
            if state_dataset_id is None:
                raise PlatformException('400', 'Must choose by "dataset_id" or "dataset_name" OR checkout a dataset')
            else:
                dataset = self.__get_by_id(state_dataset_id)
        assert isinstance(dataset, entities.Dataset)
        return dataset

    def delete(self, dataset_name=None, dataset_id=None, sure=False, really=False):
        """
        Delete a dataset forever!
        :param dataset_name: optional - search by name
        :param dataset_id: optional - search by id
        :param sure: are you sure you want to delete?
        :param really: really really?

        :return: True
        """
        if sure and really:
            dataset = self.get(dataset_name=dataset_name, dataset_id=dataset_id)
            success, response = self._client_api.gen_request(req_type='delete',
                                                             path='/datasets/{}'.format(dataset.id))
            if not success:
                raise PlatformException(response)
            logger.info('Dataset was deleted successfully')
            return True
        else:
            raise PlatformException(error='403',
                                    message='Cant delete dataset from SDK. Please login to platform to delete')

    def update(self, dataset, system_metadata=False):
        """
        Update dataset field
        :param dataset: Dataset entity
        :param system_metadata: bool
        :return: Dataset object
        """
        url_path = '/datasets/{}'.format(dataset.id)
        if system_metadata:
            url_path += '?system=true'
        success, response = self._client_api.gen_request(req_type='patch',
                                                         path=url_path,
                                                         json_req=dataset.to_json())
        if success:
            logger.info('Dataset was updated successfully')
            return dataset
        else:
            raise PlatformException(response)

    def create(self, dataset_name, labels=None, driver=None, attributes=None, ontology_ids=None):
        """
        Create a new dataset

        :param ontology_ids: optional - dataset ontology
        :param dataset_name: name
        :param attributes: dataset's ontology's attributes
        :param labels: dictionary of {tag: color} or list of label entities
        :param driver: optional
        :return: Dataset object
        """
        # labels to list
        if labels is not None:
            if not all(isinstance(label, entities.Label) for label in labels):
                labels = entities.Dataset.serialize_labels(labels)
        else:
            labels = list()
        # get creator from token
        payload = {'name': dataset_name,
                   'projects': [self.project.id]}
        if driver is not None:
            payload['driver'] = driver
        success, response = self._client_api.gen_request(req_type='post',
                                                         path='/datasets',
                                                         json_req=payload)
        if success:
            dataset = entities.Dataset.from_json(client_api=self._client_api,
                                                 _json=response.json(),
                                                 project=self.project)
            # create ontology and recipe
            dataset = dataset.recipes.create(ontology_ids=ontology_ids, labels=labels, attributes=attributes).dataset
            # # patch recipe to dataset
            # dataset = self.update(dataset=dataset, system_metadata=True)
        else:
            raise PlatformException(response)
        logger.info('Dataset was created successfully. Dataset id: {}'.format(dataset.id))
        assert isinstance(dataset, entities.Dataset)
        return dataset

    def download_annotations(self, dataset, local_path, overwrite=False):
        downloader = repositories.Downloader(self)
        return downloader.download_annotations(dataset=dataset,
                                               local_path=local_path,
                                               overwrite=overwrite)
