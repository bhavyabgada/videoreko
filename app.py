from flask import Flask, render_template, request
from werkzeug.utils import secure_filename
import key_config as keys
import time
import boto3
import json
import os

app = Flask(__name__)

s3 = boto3.client('s3',
                  aws_access_key_id=keys.ACCESS_KEY_ID,
                  aws_secret_access_key=keys.ACCESS_SECRET_KEY,
                  region_name=keys.AWS_S3_REGION_NAME
                  )

BUCKET_NAME = keys.AWS_STORAGE_BUCKET_NAME

transcribe = boto3.client('transcribe',
                          aws_access_key_id=keys.ACCESS_KEY_ID,
                          aws_secret_access_key=keys.ACCESS_SECRET_KEY,
                          region_name=keys.AWS_S3_REGION_NAME
                          )

rekognition = boto3.client('rekognition',
                           aws_access_key_id=keys.ACCESS_KEY_ID,
                           aws_secret_access_key=keys.ACCESS_SECRET_KEY,
                           region_name=keys.AWS_S3_REGION_NAME
                           )


@app.route('/')
def home():
    return render_template("index.html")


@app.route('/upload', methods=['post'])
def upload():
    if request.method == 'POST':
        img = request.files['file']
        if img:
            filename = secure_filename(img.filename)
            img.save(filename)
            key = filename

            # uploading video to s3
            s3.upload_file(
                Bucket=BUCKET_NAME,
                Filename=filename,
                Key=key
            )
            msg = "Upload Done ! "

            # Removing extension from name to transcribe
            name = os.path.splitext(filename)[0]

            # Transcribing video
            try:
                transcribe_response = transcribe.start_transcription_job(
                    TranscriptionJobName=str(name) + '-transcribe',
                    MediaFormat='mp4',
                    Media={
                        'MediaFileUri': 'https://' + BUCKET_NAME + '.s3.amazonaws.com/' + key
                    },
                    OutputBucketName=BUCKET_NAME,
                    OutputKey=str(name) + '-transcribe',
                    IdentifyLanguage=True,
                    LanguageOptions=[
                        'en-IN', 'en-US'
                    ]
                )
            except Exception as error:
                pass

            # Retrieving transcript response from s3 bucket
            transcription = None
            while transcription is None:
                try:
                    fileobj = s3.get_object(
                        Bucket=BUCKET_NAME,
                        Key=str(name) + '-transcribe')
                    filedata = fileobj['Body'].read()
                    transcription = filedata.decode('utf-8')
                    transcription = json.loads(transcription)
                    time.sleep(1)  # sometimes it takes time to generate response
                except Exception as error:
                    pass

            # Video Label Detection
            video_label_detection_job_start = rekognition.start_label_detection(
                Video={
                    'S3Object': {
                        'Bucket': BUCKET_NAME,
                        'Name': filename,
                    }
                },
                ClientRequestToken=name + '-rekolabel',
                MinConfidence=80,
                JobTag=name + '-rekolabel'
            )

            video_label_detection_job_response = rekognition.get_label_detection(
                JobId=video_label_detection_job_start['JobId'],
                SortBy='NAME'
            )

            # Video Person Tracking
            video_person_tracking_job_start = rekognition.start_person_tracking(
                Video={
                    'S3Object': {
                        'Bucket': BUCKET_NAME,
                        'Name': filename,
                    }
                },
                ClientRequestToken=name + '-rekopersontracking',
                JobTag=name + '-rekopersontracking'
            )

            status = 'IN_PROGRESS'
            while_started = time.time()
            while status != 'SUCCEEDED':
                now = time.time()
                print(now - while_started)
                video_person_tracking_job_response = rekognition.get_person_tracking(
                    JobId=video_person_tracking_job_start['JobId'],
                    SortBy='INDEX'
                )
                status = video_person_tracking_job_response['JobStatus']
                if now - while_started >= 15:
                    status = 'SUCCEEDED'

            # Preparing variables for template
            video_label_detection_job_label_list = []
            for label in video_label_detection_job_response['Labels']:
                if label['Label']['Name'] not in video_label_detection_job_label_list:
                    video_label_detection_job_label_list.append(label['Label']['Name'])

            persons_list = []
            for label in video_person_tracking_job_response['Persons']:
                if label['Person']['Index'] not in persons_list:
                    persons_list.append(label['Person']['Index'])

            no_of_persons = len(persons_list)

            # Preparing Data for index.html
            output = {
                'msg': msg,
                'transcription': transcription,
                'lang_score': float(transcription['results']['language_identification'][0]['score']),
                'video_label_detection_job_response': video_label_detection_job_response,
                'video_label_detection_job_label_list': video_label_detection_job_label_list,
                'video_person_tracking_job_response': video_person_tracking_job_response,
                'no_of_persons': no_of_persons,

            }

    return render_template("index.html", output=output)


if __name__ == "__main__":
    app.run(debug=True)
