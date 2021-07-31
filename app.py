from flask import Flask, render_template, request
from werkzeug.utils import secure_filename
import key_config as keys
import time
import boto3
import json
import os
from grammarbot import GrammarBotClient
import pandas as pd

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

comprehend = boto3.client('comprehend',
                          aws_access_key_id=keys.ACCESS_KEY_ID,
                          aws_secret_access_key=keys.ACCESS_SECRET_KEY,
                          region_name=keys.AWS_S3_REGION_NAME
                          )

grammarbotclient = GrammarBotClient()
grammarbotclient = GrammarBotClient(api_key=keys.GRAMMARBOT_API_KEY)  # GrammarBotClient(api_key=my_api_key_here)
client = GrammarBotClient(base_uri=keys.GRAMMARBOT_URI)


# rekognition = boto3.client('rekognition',
#                            aws_access_key_id=keys.ACCESS_KEY_ID,
#                            aws_secret_access_key=keys.ACCESS_SECRET_KEY,
#                            region_name=keys.AWS_S3_REGION_NAME
#                            )


@app.route('/')
def home():
    return render_template("index.html")


@app.route('/upload', methods=['post'])
def upload():
    if request.method == 'POST':
        img = request.files['file']
        phrase = request.form['phrase']
        phrase = phrase.split(',')
        ipa = request.form['ipa']
        ipa = ipa.split(',')
        displayas = request.form['displayas']
        displayas = displayas.split(',')
        df = pd.DataFrame(list(zip(phrase, ipa, displayas)))
        # df.drop(df.tail(1).index, inplace=True)


        if img:
            filename = secure_filename(img.filename)
            img.save(filename)
            key = filename
            name = os.path.splitext(filename)[0]
            df.to_csv(name+'.txt', header=None, index=None, sep='\t', mode='w')
            s3.upload_file(
                Bucket=BUCKET_NAME,
                Filename=name+'.txt',
                Key=name+'.txt'
            )

            # uploading video to s3
            s3.upload_file(
                Bucket=BUCKET_NAME,
                Filename=filename,
                Key=key
            )

            msg = "Upload Done ! "

            # Removing extension from name to transcribe

            # try:
            #     customizable_filter = transcribe.get_vocabulary_filter(
            #         VocabularyFilterName=str(name) + '-vocabularyfilter'
            #     )
            # except:
            #     customizable_filter = transcribe.create_vocabulary_filter(
            #         VocabularyFilterName=str(name) + '-vocabularyfilter',
            #         LanguageCode='en-US',
            #         Words=[
            #             customvocabulary,
            #         ],
            #     )

            # if customizable_filter:
            #     try:
            #         transcribe_response = transcribe.start_transcription_job(
            #             TranscriptionJobName=str(name) + '-transcribe',
            #             MediaFormat='mp4',
            #             Media={
            #                 'MediaFileUri': 'https://' + BUCKET_NAME + '.s3.amazonaws.com/' + key
            #             },
            #             OutputBucketName=BUCKET_NAME,
            #             OutputKey=str(name) + '-transcribe',
            #             Settings={
            #                 'ShowSpeakerLabels': True,
            #                 'MaxSpeakerLabels': 123,
            #                 'VocabularyFilterName': str(name) + '-vocabularyfilter',
            #                 'VocabularyFilterMethod': 'tag'
            #             },
            #             IdentifyLanguage=True,
            #             LanguageOptions=[
            #                 'en-IN', 'en-US'
            #             ]
            #         )
            #     except Exception as error:
            #         pass
            # else:
            # Transcribing video

            try:
                get_vocabulary = transcribe.get_vocabulary(
                    VocabularyName=str(name) + '-vocabulary',
                )
            except:
                get_vocabulary = transcribe.create_vocabulary(
                    VocabularyName=str(name) + '-vocabulary',
                    LanguageCode='en-US',
                    VocabularyFileUri='https://' + BUCKET_NAME + '.s3.amazonaws.com/' + name + '.txt',
                )







            print(get_vocabulary['VocabularyState'])

            if get_vocabulary['VocabularyState'] == 'PENDING':
                return 'Vocabulary State = '+ get_vocabulary['VocabularyState']

            if get_vocabulary['VocabularyState'] == 'FAILED':
                delete_vocabulary = transcribe.delete_vocabulary(
                    VocabularyName=str(name) + '-vocabulary',
                )
                return 'Vocabulary State = '+ get_vocabulary['VocabularyState'] + '. Please retry with correct vocabulary!'



            transcribe_response = transcribe.start_transcription_job(
                TranscriptionJobName=str(name) + '-transcribe',
                MediaFormat='mp4',
                Media={
                    'MediaFileUri': 'https://' + BUCKET_NAME + '.s3.amazonaws.com/' + key
                },
                Settings={
                            'VocabularyName': str(name) + '-vocabulary'
                                },
                OutputBucketName=BUCKET_NAME,
                OutputKey=str(name) + '-transcribe',
                LanguageCode=get_vocabulary['LanguageCode']

            )



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

            detect_syntax = comprehend.detect_syntax(
                Text=transcription['results']['transcripts'][0]['transcript'],
                LanguageCode='en',
            )
            detect_sentiment = comprehend.detect_sentiment(
                Text=transcription['results']['transcripts'][0]['transcript'],
                LanguageCode='en',
            )
            detect_pii_entities = comprehend.detect_pii_entities(
                Text=transcription['results']['transcripts'][0]['transcript'],
                LanguageCode='en',
            )
            detect_key_phrases = comprehend.detect_key_phrases(
                Text=transcription['results']['transcripts'][0]['transcript'],
                LanguageCode='en',
            )
            detect_entities = comprehend.detect_entities(
                Text=transcription['results']['transcripts'][0]['transcript'],
                LanguageCode='en',
            )
            detect_dominant_language = comprehend.detect_dominant_language(
                Text=transcription['results']['transcripts'][0]['transcript'],
            )



            if get_vocabulary['VocabularyState']=='READY':

                delete_vocabulary = transcribe.delete_vocabulary(
                    VocabularyName=str(name) + '-vocabulary',
                )
                response = transcribe.delete_transcription_job(
                    TranscriptionJobName=str(name) + '-transcribe'
                )
                response = s3.delete_object(
                    Bucket=BUCKET_NAME,
                    Key=str(name) + '-transcribe',
                )
                response = s3.delete_object(
                    Bucket=BUCKET_NAME,
                    Key=str(filename),
                )
                response = s3.delete_object(
                    Bucket=BUCKET_NAME,
                    Key=str(name) + '.txt',
                )


            grammarbot = grammarbotclient.check(transcription['results']['transcripts'][0]['transcript'])
            grammarbot_results = grammarbot.matches
            grammarbot_results_list = []
            for item in grammarbot_results:
                grammarbot_results_list.append({

                    'rule': item.rule,
                    'category': item.category,
                    'type': item.type,
                    'message': item.message,

                    'replacements': item.replacements,
                    'replacement_offset': item.replacement_offset,
                    'replacement_length': item.replacement_length,

                    'corrections': item.corrections,
                })


            # # Video Label Detection
            # video_label_detection_job_start = rekognition.start_label_detection(
            #     Video={
            #         'S3Object': {
            #             'Bucket': BUCKET_NAME,
            #             'Name': filename,
            #         }
            #     },
            #     ClientRequestToken=name + '-rekolabel',
            #     MinConfidence=80,
            #     JobTag=name + '-rekolabel'
            # )
            #
            # video_label_detection_job_response = rekognition.get_label_detection(
            #     JobId=video_label_detection_job_start['JobId'],
            #     SortBy='NAME'
            # )
            #
            # # Video Person Tracking
            # video_person_tracking_job_start = rekognition.start_person_tracking(
            #     Video={
            #         'S3Object': {
            #             'Bucket': BUCKET_NAME,
            #             'Name': filename,
            #         }
            #     },
            #     ClientRequestToken=name + '-rekopersontracking',
            #     JobTag=name + '-rekopersontracking'
            # )
            #
            # video_person_tracking_job_response = rekognition.get_person_tracking(
            #     JobId=video_person_tracking_job_start['JobId'],
            #     SortBy='INDEX'
            # )
            #
            # # Preparing variables for template
            # video_label_detection_job_label_list = []
            # for label in video_label_detection_job_response['Labels']:
            #     if label['Label']['Name'] not in video_label_detection_job_label_list:
            #         video_label_detection_job_label_list.append(label['Label']['Name'])
            #
            # persons_list = []
            # for label in video_person_tracking_job_response['Persons']:
            #     if label['Person']['Index'] not in persons_list:
            #         persons_list.append(label['Person']['Index'])
            #
            # no_of_persons = len(persons_list)

            # Preparing Data for index.html
            output = {
                'msg': msg,
                'transcription': transcription,
                'lang_score': 1,
                # 'video_label_detection_job_response': video_label_detection_job_response,
                # 'video_label_detection_job_label_list': video_label_detection_job_label_list,
                # 'video_person_tracking_job_response': video_person_tracking_job_response,
                # 'no_of_persons': no_of_persons,
                # 'customizable_filter': customizable_filter
                'detect_syntax': detect_syntax,
                'detect_sentiment': detect_sentiment,
                'detect_pii_entities': detect_pii_entities,
                'detect_key_phrases': detect_key_phrases,
                'detect_entities': detect_entities,
                'detect_dominant_language': detect_dominant_language,
                'grammarbot_results_list': grammarbot_results_list,
                'get_vocabulary':get_vocabulary,
                'languageCode':get_vocabulary['LanguageCode'],

            }

        return render_template("index.html", output=output)
    return 'Please upload video.'


if __name__ == "__main__":
    app.run(debug=True)
