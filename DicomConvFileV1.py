from fileinput import filename
import os
from pickle import FALSE, TRUE
import shutil
import smtplib
import time
import sys
import logging
from watchdog.observers.polling import PollingObserver as Observer
from watchdog.events import FileSystemEventHandler
from Dicom2jpgV1 import DicomTojpg  # Neuer DICOM->JPG Support (V10.1)

def email_senden(mail_text): 
    try:
        # mail_text = "Fehler in File-Konversion OCT File " +  file_name + file_ext
        server = smtplib.SMTP('asmtp.mail.hostpoint.ch', 587)
        server.login(user, pwd)
        Data = "From:%s\nTo:%s\nSubject:%s\n\n%s" %(Mail_from, Rcpt_to, subject, mail_text)
        # print(Data)
        # sendmail kann nur ascii-Zeichen verwerten, also insb. keine Umlaute etc., daher diese eliminieren: 
        Data = Data.encode("ascii", "ignore")
        # print("Data erstellt mit ascii ignore:")
        # print(Data)
        server.sendmail(Mail_from, Rcpt_to, Data)
        server.quit()
    except:
        print("email senden ergab fehler")
        logger.debug("email error in file "+file_name+file_ext, exc_info=True)
        logger.info("email senden ergab Fehler")    

class Handler(FileSystemEventHandler):
    def on_modified(self, event):
        global to_continue
        global file_name
        global file_ext
        os.chdir(Src_path)
        list = os.listdir('.')
        number_files = len(list)
        # print(number_files)
        for f in list: 
            file_name, file_ext = os.path.splitext(f)
            # --- DICOM -> JPG (neu in V10.1) ---
            if file_ext.lower() == '.dcm':
                try:
                    Cirrus_Bildergalerie = os.path.join(Dst_path, 'Cirrus_Bildergalerie')
                    src_file = os.path.join(Src_path, f)
                    res = DicomTojpg(src_file, out_dir=Cirrus_Bildergalerie)
                    if res:
                        logger.info('DICOM verarbeitet: %s', res)
                    else:
                        logger.warning('DICOM-Verarbeitung fehlgeschlagen: %s', f)
                except Exception:
                    logger.error('Fehler bei DICOM-Verarbeitung: %s', f, exc_info=True)
                    try:
                        email_senden('Fehler in DICOM-Konversion ' + f)
                    except Exception:
                        pass
                continue

            #print(file_name.split('_'), file_ext)
            if (file_ext == '.pdf') or (file_ext ==".tiff"):
                try: 
                    allocated = False
                    if file_name.count('_') == 10: 
                        Vorname, Name, Dummy, PatID, Geburtsdatum, Geschlecht, Untersuchung, Untersuchungsdatum, Seite, Analyse, AnalyseDatum = file_name.split('_')
                        Geburtsdatum_short = Geburtsdatum[0:7]
                        Untersuchungsdatum_short = Untersuchungsdatum[0:7]
                        AnalyseDatum_short = AnalyseDatum[0:7]
                        New_file_name = Vorname + '_' + Name + '_' + Geburtsdatum_short + '_' + Untersuchungsdatum_short + '_' + Seite +'_' + Analyse + '_' + AnalyseDatum_short + '_' + PatID
                    elif file_name.count('_') == 11:
                        Vorname, Vorname2, Name, Dummy, PatID, Geburtsdatum, Geschlecht, Untersuchung, Untersuchungsdatum, Seite, Analyse, AnalyseDatum = file_name.split('_')
                        Geburtsdatum_short = Geburtsdatum[0:7]
                        Untersuchungsdatum_short = Untersuchungsdatum[0:7]
                        AnalyseDatum_short = AnalyseDatum[0:7]
                        New_file_name = Vorname + '_' + Vorname2 + '_' + Name + '_' + Geburtsdatum_short + '_' + Untersuchungsdatum_short + '_' + Seite +'_' + Analyse + '_' + AnalyseDatum_short + '_' + PatID
                    else:
                        Vorname, Vorname2, Vorname3, Name, Dummy, PatID, Geburtsdatum, Geschlecht, Untersuchung, Untersuchungsdatum, Seite, Analyse, AnalyseDatum = file_name.split('_')
                        Geburtsdatum_short = Geburtsdatum[0:7]
                        Untersuchungsdatum_short = Untersuchungsdatum[0:7]
                        AnalyseDatum_short = AnalyseDatum[0:7]
                        New_file_name = Vorname + '_' + Vorname2 + '_' + Vorname3 + '_'+ Name + '_' + Geburtsdatum_short + '_' + Untersuchungsdatum_short + '_' + Seite +'_' + Analyse + '_' + AnalyseDatum_short + '_' + PatID
                    for x in range(len(OCT_analysen)):
                        #print(allocated)
                        if (OCT_analysen[x] in Analyse and allocated == False): 
                            Dst_path_folder = Dst_path + Dst_folders[x] + "/" 
                            allocated = True
                            # print(allocated)
                            # print(Dst_path_folder)
                    if allocated == False: 
                        Dst_path_folder = Dst_path + Dst_folders[4] + "/" #in doubt, put file in Dst_folder no 4, i.e. Pachymetrie
                        Logmessage = "File "+file_name+file_ext + " not allocated correctly, allocation to default folder " + Dst_path_folder
                        print(Logmessage)
                        logger.info(Logmessage)
                    #else: 
                    #    print("allocated")
                    #print(New_file_name)
                    #print(Dst_path_folder + New_file_name + file_ext)
                    #print(os.listdir(Dst_path))
                    #os.rename(Src_path + file_name + file_ext, Dst_path + New_file_name + file_ext)
                    #print("trying os.chdir(Dst_path_folder) with " + Dst_path_folder)
                    #os.chdir(Dst_path_folder)
                    #print("os.chdir(Dst_path_folder)")
                    #print(os.listdir())
                    #print(Dst_path_folder + New_file_name + file_ext)
                    # Hier muessen wir zuerst den Filenamen aendern und dann in einem 2. Schritt das 
                    # File verschieben, da ansonsten Fehler wegen moeglicherweise zu langen Filnamen entstehen
                    os.rename(Src_path+file_name+file_ext, Src_path+New_file_name+file_ext)
                    Logmessage = "File " + Src_path+file_name+file_ext + " renamed in " + Src_path+New_file_name+file_ext
                    logger.info(Logmessage)
                    shutil.move(Src_path + New_file_name + file_ext, Dst_path_folder + New_file_name + file_ext)
                    print(time.asctime() + ":" + "File " + New_file_name + file_ext + " moved to " + Dst_path_folder)
                    Logmessage = "File " + New_file_name + file_ext + " moved to " + Dst_path_folder
                    logger.info(Logmessage)
                except:
                    print('rename has not worked with file ' + file_name)
                    logger.debug("exception error in file renaming occurred with file "+file_name+file_ext, exc_info=True)
                    # send a mail
                    email_senden("Fehler in File-Konversion OCT File " +  file_name + file_ext)
                    
            if file_ext == ".stop":
                to_continue = False
                #print(to_continue)
                #if to_continue: 
                #    print("to_continue is still True")
                #if to_continue == False:
                #    print("to_continue ist set False")
                observer.stop()
                stop_message = time.asctime() + " FilenameConv Cirrus beendet durch .stop"
                print(stop_message)
                email_senden(stop_message)
                logger.info(stop_message)
                #sys.exit()


#create and configure logger; logger did not yet work!
LOG_FORMAT = "%(levelname)s %(asctime)s - %(message)s"
logging.basicConfig(filename = '/volume1/Team/OCTFiles/FileNameConv/FilenameConv.log', level =logging.DEBUG, format = LOG_FORMAT)
logger = logging.getLogger()

#print(os.getcwd())
# Src_path = ('/Volumes/Team/OCTFiles/FilesFromCirrus/') # Aktivieren, falls vom Mac ausgeführt
Src_path = ('/volume1/Team/OCTFiles/FilesFromCirrus/') # Aktivieren, falls vom NAS ausgeführt
# Dst_path = ('S:\\OCTFiles\\FilesForSimed\\')
# Dst_path = ('/Volumes/Team/OCTFiles/FilesForSimed/') # Aktivieren, falls vom Mac aus ausgeführt
Dst_path = ('/volume1/Team/OCTFiles/FilesForSimed/') # Aktivieren, falls vom NAS direkt ausgeführt
Dst_folders = ["OCT_Progressionsanalysen", "Ganglienzellanalysen", "OCT_Makula", "OCT_Papillen", "Pachymetrie", "Vorderkammer_OCT"]
Dst_path_folder =""
OCT_analysen = ["Progression", "Ganglion", "Macula", "RNFL", "Pachy", "Anterior Segment Analysis"]
#os.chdir(Dst_path)
#print(os.listdir())

# Vorbereitung für Fehler-Emails
user = "nas@augenarzt-meierhofplatz.ch"
pwd = "Praxis-2021!"
subject = "Meldung von Cirrus File Konversion"
Mail_from ="nas@augenarzt-meierhofplatz.ch"
Rcpt_to = "info@augenarzt-meierhofplatz.ch"
server = smtplib.SMTP('asmtp.mail.hostpoint.ch:587')



# Aktivierung des Observers etc.
observer = Observer()
event_handler = Handler()
observer.schedule(event_handler, Src_path, recursive=True)
print(time.asctime() + ":" + 'starting')
email_senden("FileNameConv Cirrus gestartet")
observer.start()
to_continue = True

try: 
    while to_continue:
        time.sleep(10)
        #print(time.asctime())
        #print(to_continue)
except KeyboardInterrupt:
    observer.stop()
observer.join()
    

print('done')


