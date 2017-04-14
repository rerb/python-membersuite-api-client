from retrying import retry
import datetime

from .exceptions import ExecuteMSQLError

RETRY_ATTEMPTS = 10


@retry(stop_max_attempt_number=RETRY_ATTEMPTS, wait_fixed=2000)
def run_query(client, base_query, start_record, limit_to, verbose=False):
    """inline method to take advantage of retry"""
    if verbose:
        print("[start: %d limit: %d]" % (start_record, limit_to))
    start = datetime.datetime.now()
    result = client.runSQL(query=base_query,
                           start_record=start_record,
                           limit_to=limit_to)
    end = datetime.datetime.now()
    if verbose:
        print("[%s - %s]" % (start, end))
    return result


class ChunkQueryMixin(object):
    """
    A mixin for API client service classes that makes it easy to consistently
    request multiple queries from a MemberSuite endpoint.

    Membersuite will often time out on big queries, so this allows us to
    break it up into smaller requests.

    Design assumptions:
        - The service defines an `result_to_models` method to "transform"
        the objects returned by the endpoint
    """

    def get_long_query(self, base_query, limit_to=100, max_calls=None,
                       start_record=0, verbose=False):
        """
        Takes a base query for all objects and recursively requests them

        :param str base_query: the base query to be executed
        :param int limit_to: how many rows to query for in each chunk
        :param int max_calls: the max calls(chunks to request) None is infinite
        :param int start_record: the first record to return from the query
        :param bool verbose: print progress to stdout
        :return: a list of Organization objects
        """

        if verbose:
            print(base_query)

        record_index = start_record
        result = run_query(self.client, base_query, record_index,
                           limit_to, verbose)
        mysql_result = result['body']["ExecuteMSQLResult"]
        try:
            obj_result = mysql_result["ResultValue"]["ObjectSearchResult"]
            result_set = obj_result["Objects"]["MemberSuiteObject"]
        except TypeError as e:
            raise ExecuteMSQLError(result['body']["ExecuteMSQLResult"])
        all_objects = self.result_to_models(result)
        call_count = 1
        """
        continue to run queries as long as we
            - don't exceed the call call_count
            - don't see results that are less than the limited length (the end)
        """
        while call_count != max_calls and len(result_set) >= limit_to:

            record_index += len(result_set)  # should be `limit_to`
            result = run_query(self.client, base_query, record_index,
                               limit_to, verbose)
            result_set = result['body']["ExecuteMSQLResult"]\
                ["ResultValue"]["ObjectSearchResult"]["Objects"]\
                ["MemberSuiteObject"]
            all_objects += self.result_to_models(result)
            call_count += 1

        return all_objects

    def result_to_models(self, result):
        """
            this is the 'transorm' part of ETL:
            converts the result of the SQL to Models
        """
        mysql_result = result['body']['ExecuteMSQLResult']

        if not mysql_result['Errors']:
            obj_result = mysql_result['ResultValue']['ObjectSearchResult']
            if not obj_result['Objects']:
                return []
            objects = obj_result['Objects']['MemberSuiteObject']

            model_list = []
            for obj in objects:
                model = self.ms_object_to_model(obj)
                model_list.append(model)

            return model_list

        else:
            raise ExecuteMSQLError(result)
