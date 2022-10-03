import io
import os
import json
import logging

import sys
from fdk import response

import oci
import pandas as pd
import numpy as np
import datetime
funcDefinition = {
    "status": {
        "returnCode": 0,
        "errorMessage": ""
    },
    "funcDescription": {
        "outputs": [
            {"name": "save_result", "dataType": "varchar(100)"}
        ],
        "parameters": [
            {"name": "title", "displayName": "Title Column",
             "description": "Specify Title for Dataset", "required": True,
             "value": {"type": "string"}}
        ],
        "bucketName": "bucket-ivy-FAAS",
        "isOutputJoinableWithInput": False
    }
}

def save_result(text):
    return "OK"

def handler(ctx, data: io.BytesIO = None):
    response_data = ""
    try:
        body = json.loads(data.getvalue())
        funcMode = body.get("funcMode")
        if funcMode == 'describeFunction':
           response_data = json.dumps(funcDefinition)
        elif funcMode == "executeFunction":
            input_method = body.get("input").get("method")
            if input_method == "csv":
                bucketName = body.get("input").get("bucketName")
                fileName = body.get("input").get("fileName") + body.get("input").get("fileExtension")
                # rowID = body.get("input").get("rowID")
                args = body.get("args")

                input_csv_path = read_from_objectstore(bucketName, fileName)
                dat = pd.read_csv(input_csv_path, sep=",", quotechar="\"", encoding="utf-8", parse_dates=True, infer_datetime_format=True)


                bucketName1 = "bucket-ivy01-FAAS"
                dt = datetime.datetime.now()
                s = dt.strftime("%Y-%m-%d %H:%M:%S")
                output_dat1 = dat.drop(["row_id"], axis=1)

                outputFile1 = body.get("output").get("fileName") + body.get("output").get("fileExtension")
                output_csv_path1 = "/tmp/" + outputFile1
                output_dat1.to_csv(output_csv_path1, index=False )
                dstitle = args.get("title")
                tt_outputFile = dstitle+s+ ".csv"
                write_to_objectstore(bucketName1, tt_outputFile, output_csv_path1)


                dat2 = dat.head(1)
                output_dat = pd.DataFrame(np.vectorize(save_result)(dat2["row_id"]), columns =['save_result'])
                outputFile = body.get("output").get("fileName") + body.get("output").get("fileExtension")
                output_csv_path  = "/tmp/"+outputFile
                # output_dat.to_csv(output_csv_path, index=True, index_label=rowID)


                output_dat.to_csv(output_csv_path, index=False)

                write_to_objectstore(bucketName, outputFile, output_csv_path)

                os.remove(input_csv_path)
                os.remove(output_csv_path)
                response_data = prepareResponse(bucketName, outputFile)
            else:
                response_data = prepareResponseError("input method not supported: " + input_method)
        else:
            response_data = prepareResponseError("Invalid funcMode: " + funcMode)
    except (Exception, ValueError) as ex:
        response_data = prepareResponseError("Error while executing " + ex)

    return response.Response(
        ctx, response_data,
        headers={"Content-Type": "application/json"}
    )
def prepareResponse(bucketName, outputFile):
    ret_template = """{
        "status": {
            "returnCode": "",
            "errorMessage": ""
            }
        }"""
    ret_json = json.loads(ret_template)
    ret_json["status"]["returnCode"] = 0
    ret_json["status"]["errorMessage"] = ""
    return json.dumps(ret_json)

def prepareResponseError(errorMsg):
    ret_template = """{
        "status": {
            "returnCode": "",
            "errorMessage": ""
            }
        }"""
    ret_json = json.loads(ret_template)
    ret_json["status"]["returnCode"] = -1
    ret_json["status"]["errorMessage"] = errorMsg
    return json.dumps(ret_json)

def get_object(bucketName, objectName):
    signer = oci.auth.signers.get_resource_principals_signer()
    client = oci.object_storage.ObjectStorageClient(config={}, signer=signer)
    namespace = client.get_namespace().data
    try:
        print("Searching for bucket and object", flush=True)
        object = client.get_object(namespace, bucketName, objectName)
        print("found object", flush=True)
        if object.status == 200:
            print("Success: The object " + objectName + " was retrieved with the content: " + object.data.text, flush=True)
            message = object.data.text
        else:
            message = "Failed: The object " + objectName + " could not be retrieved."
    except Exception as e:
        message = "Failed: " + str(e.message)
    return { "content": message }


def read_from_objectstore(bucket_name, file_name):
    try:
        logging.getLogger().info(
            "reading from object storage {}:{}".format(bucket_name, file_name))
        signer = oci.auth.signers.get_resource_principals_signer()
        object_storage = oci.object_storage.ObjectStorageClient(config={}, signer=signer)
        namespace = object_storage.get_namespace().data
        obj = object_storage.get_object(namespace, bucket_name, file_name)
        file = open('/tmp/'+file_name, "wb")
        for chunk in obj.data.raw.stream(2048 ** 2, decode_content=False):
            file.write(chunk)
        file.close()
        return '/tmp/'+file_name
    except Exception as e:
        print("Error found\n")
        print(e)
        return None

def write_to_objectstore(bucket_name, file_name, source_file):
    logging.getLogger().info("Writing to object storage {}:{}".format(bucket_name, file_name))
    signer = oci.auth.signers.get_resource_principals_signer()
    object_storage = oci.object_storage.ObjectStorageClient(config={}, signer=signer)
    namespace = object_storage.get_namespace().data
    with open(source_file, 'rb') as f:
        obj = object_storage.put_object(namespace, bucket_name, file_name, f)