from fileinput import filename
import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("GOTO_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
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
        server = smtplib.SMTP('asmtp.mail.hostpoint.ch', 587, timeout=30)
        server.ehlo()
        server.starttls()
        server.ehlo()
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
        print("email senden ergab fehler", flush=True)
        logger.debug("email error: %s", mail_text, exc_info=True)
        logger.info("email senden ergab Fehler")    

# Dateien, die gerade konvertiert werden. Sonst loest dasselbe File
# created und modified aus und wird zweimal verarbeitet.
_in_progress = set()

def _wait_until_written(path):
    """Wartet, bis die Datei nicht mehr waechst (Kopie noch nicht fertig)."""
    previous = None
    same = 0
    for _ in range(20):
        if not os.path.isfile(path):
            return False
        size = os.path.getsize(path)
        if size > 0 and size == previous:
            same += 1
            if same >= 2:
                return True
        else:
            same = 0
            previous = size
        time.sleep(0.5)
    return os.path.isfile(path) and os.path.getsize(path) > 0

def _archive_dcm(path):
    """Verschiebt die Quelle aus dem Watch-Ordner, damit sie nicht erneut konvertiert wird."""
    archive = os.path.join(Dst_path, "Cirrus_DICOM_archiv")
    os.makedirs(archive, exist_ok=True)
    dest = os.path.join(archive, os.path.basename(path))
    if os.path.exists(dest):
        stem, ext = os.path.splitext(os.path.basename(path))
        dest = os.path.join(archive, "%s_%s%s" % (stem, int(time.time()), ext))
    shutil.move(path, dest)
    logger.info("DICOM archiviert: %s", dest)

def _stop_observer(reason):
    global to_continue
    to_continue = False
    stop_message = time.asctime() + " " + reason
    print(stop_message)
    email_senden(stop_message)
    logger.info(stop_message)
    if observer.is_alive():
        observer.stop()

def _handle_path(path):
    global file_name
    global file_ext
    if not path or os.path.isdir(path):
        return
    file_name, file_ext = os.path.splitext(os.path.basename(path))
    if file_ext == ".stop":
        _stop_observer("FilenameConv Cirrus beendet durch .stop")
        return
    if file_ext.lower() != ".dcm":
        return
    key = os.path.abspath(path)
    if key in _in_progress:
        return
    _in_progress.add(key)
    try:
        if not _wait_until_written(path):
            logger.warning("DICOM nicht lesbar oder noch nicht fertig: %s", path)
            return
        Cirrus_Bildergalerie = os.path.join(Dst_path, "Cirrus_Bildergalerie")
        res = DicomTojpg(path, out_dir=Cirrus_Bildergalerie)
        if res:
            logger.info("DICOM verarbeitet: %s", res)
            _archive_dcm(path)
        else:
            logger.warning("DICOM-Verarbeitung fehlgeschlagen: %s", path)
    except Exception:
        logger.error("Fehler bei DICOM-Verarbeitung: %s", path, exc_info=True)
        try:
            email_senden("Fehler in DICOM-Konversion " + os.path.basename(path))
        except Exception:
            pass
    finally:
        _in_progress.discard(key)

class Handler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            _handle_path(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            _handle_path(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            _handle_path(event.dest_path)

# PDF/TIFF-Umbenennung bleibt auskommentiert (passiv).
# print(file_name.split('_'), file_ext)
            # if (file_ext == '.pdf') or (file_ext ==".tiff"):
                # try: 
                    # allocated = False
                    # if file_name.count('_') == 10: 
                        # Vorname, Name, Dummy, PatID, Geburtsdatum, Geschlecht, Untersuchung, Untersuchungsdatum, Seite, Analyse, AnalyseDatum = file_name.split('_')
                        # Geburtsdatum_short = Geburtsdatum[0:7]
                        # Untersuchungsdatum_short = Untersuchungsdatum[0:7]
                        # AnalyseDatum_short = AnalyseDatum[0:7]
                        # New_file_name = Vorname + '_' + Name + '_' + Geburtsdatum_short + '_' + Untersuchungsdatum_short + '_' + Seite +'_' + Analyse + '_' + AnalyseDatum_short + '_' + PatID
                    # elif file_name.count('_') == 11:
                        # Vorname, Vorname2, Name, Dummy, PatID, Geburtsdatum, Geschlecht, Untersuchung, Untersuchungsdatum, Seite, Analyse, AnalyseDatum = file_name.split('_')
                        # Geburtsdatum_short = Geburtsdatum[0:7]
                        # Untersuchungsdatum_short = Untersuchungsdatum[0:7]
                        # AnalyseDatum_short = AnalyseDatum[0:7]
                        # New_file_name = Vorname + '_' + Vorname2 + '_' + Name + '_' + Geburtsdatum_short + '_' + Untersuchungsdatum_short + '_' + Seite +'_' + Analyse + '_' + AnalyseDatum_short + '_' + PatID
                    # else:
                        # Vorname, Vorname2, Vorname3, Name, Dummy, PatID, Geburtsdatum, Geschlecht, Untersuchung, Untersuchungsdatum, Seite, Analyse, AnalyseDatum = file_name.split('_')
                        # Geburtsdatum_short = Geburtsdatum[0:7]
                        # Untersuchungsdatum_short = Untersuchungsdatum[0:7]
                        # AnalyseDatum_short = AnalyseDatum[0:7]
                        # New_file_name = Vorname + '_' + Vorname2 + '_' + Vorname3 + '_'+ Name + '_' + Geburtsdatum_short + '_' + Untersuchungsdatum_short + '_' + Seite +'_' + Analyse + '_' + AnalyseDatum_short + '_' + PatID
                    # for x in range(len(OCT_analysen)):
                        # #print(allocated)
                        # if (OCT_analysen[x] in Analyse and allocated == False): 
                            # Dst_path_folder = Dst_path + Dst_folders[x] + "/" 
                            # allocated = True
                            # # print(allocated)
                            # # print(Dst_path_folder)
                    # if allocated == False: 
                        # Dst_path_folder = Dst_path + Dst_folders[4] + "/" #in doubt, put file in Dst_folder no 4, i.e. Pachymetrie
                        # Logmessage = "File "+file_name+file_ext + " not allocated correctly, allocation to default folder " + Dst_path_folder
                        # print(Logmessage)
                        # logger.info(Logmessage)
                    # #else: 
                    # #    print("allocated")
                    # #print(New_file_name)
                    # #print(Dst_path_folder + New_file_name + file_ext)
                    # #print(os.listdir(Dst_path))
                    # #os.rename(Src_path + file_name + file_ext, Dst_path + New_file_name + file_ext)
                    # #print("trying os.chdir(Dst_path_folder) with " + Dst_path_folder)
                    # #os.chdir(Dst_path_folder)
                    # #print("os.chdir(Dst_path_folder)")
                    # #print(os.listdir())
                    # #print(Dst_path_folder + New_file_name + file_ext)
                    # # Hier muessen wir zuerst den Filenamen aendern und dann in einem 2. Schritt das 
                    # # File verschieben, da ansonsten Fehler wegen moeglicherweise zu langen Filnamen entstehen
                    # os.rename(Src_path+file_name+file_ext, Src_path+New_file_name+file_ext)
                    # Logmessage = "File " + Src_path+file_name+file_ext + " renamed in " + Src_path+New_file_name+file_ext
                    # logger.info(Logmessage)
                    # shutil.move(Src_path + New_file_name + file_ext, Dst_path_folder + New_file_name + file_ext)
                    # print(time.asctime() + ":" + "File " + New_file_name + file_ext + " moved to " + Dst_path_folder)
                    # Logmessage = "File " + New_file_name + file_ext + " moved to " + Dst_path_folder
                    # logger.info(Logmessage)
                # except:
                    # print('rename has not worked with file ' + file_name)
                    # logger.debug("exception error in file renaming occurred with file "+file_name+file_ext, exc_info=True)
                    # # send a mail
                    # email_senden("Fehler in File-Konversion OCT File " +  file_name + file_ext)


# Mac: gemountetes Team-Volume. Sonst Synology (Linux) unter /volume1.
if sys.platform == "darwin":
    _oct_root = "/Volumes/Team/OCTFiles"
else:
    _oct_root = "/volume1/Team/OCTFiles"

print(time.asctime() + ": starting", flush=True)

#create and configure logger; logger did not yet work!
LOG_FORMAT = "%(levelname)s %(asctime)s - %(message)s"
logging.basicConfig(filename = _oct_root + "/FileNameConv/FilenameConv.log", level =logging.DEBUG, format = LOG_FORMAT)
logger = logging.getLogger()

#print(os.getcwd())
Src_path = _oct_root + "/FilesFromCirrus/"
print
Dst_path = _oct_root + "/FilesForSimed/"
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

# Aktivierung des Observers etc.
observer = Observer()
event_handler = Handler()
observer.schedule(event_handler, Src_path, recursive=True)
to_continue = True
email_senden("FileNameConv Cirrus gestartet")

# Dateien, die schon im Ordner liegen, einmal verarbeiten.
# Danach nur noch das einzelne Event-File, nicht den ganzen Ordner.
for _name in os.listdir(Src_path):
    _handle_path(os.path.join(Src_path, _name))
    if not to_continue:
        break

if to_continue:
    observer.start()
    try:
        while to_continue:
            time.sleep(10)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    

print('done')


