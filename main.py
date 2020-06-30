"""
利用processOn 支持倒入pos文件的功能，实现 文件的下载和倒入 突破文件数限制

self_file_max_num  processOn文件数限制
self_pos_path  保持路径

list local 查看本地文件
list online 查询线上文件
download all 下载所有线上文件到本地 并删除
import {title}  导入到线上   title 是 list local中的文件名
import path   导入文件到线上

"""
import requests
import json
import collections
from collections import OrderedDict
import os
import logging
from urllib.parse import quote

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(filename)s[line:%(lineno)d] - %(levelname)s: %(message)s')

ProcessOnFile = collections.namedtuple("FileVo", ["chartId", "title", "last_modify"])

self_pos_path = 'user'
self_file_max_num = 1
user_name = ""

password = ""
file_name_split = '_'


def http_response_valid(resp, success_status):
    if success_status == resp.status_code:
        logging.info("http url:{%s} success" % resp.request.url)
        return True
    logging.error("http url:{%s} error:status_code:%d" % (resp.request.url, resp.status_code))
    logging.error(resp.text)
    return False


def parse_file_id(location):
    return location.split('?')[0].split('/')[2]


class ProcessOn:
    def __init__(self, user_name, password):
        self.user_name = user_name
        self.password = password
        self.ss = requests.Session()
        self.path = os.path.join(os.path.dirname(__file__), self_pos_path)
        if not os.path.exists(self.path):
            os.mkdir(self.path)
        self.online_file_dict = dict()
        self.local_file_dict = dict()
        self.cookies_path = os.path.join(os.path.dirname(__file__), self.user_name + "_cookies.txt")
        self.uk = None
        self.refresh()

    def refresh(self):
        """
        刷新 维护的文件集合
        :return:
        """
        self.login()
        self.online_file_dict = dict()
        self.local_file_dict = dict()
        self.get_online_file_list()
        for file_name in os.listdir(self.path):
            real_path = os.path.join(self.path, file_name)
            if os.path.isfile(real_path):
                title, last_modify = file_name.split("_")
                if title in self.online_file_dict.keys():
                    os.remove(real_path)
                    continue
                if title in self.local_file_dict.keys():
                    exist_file = self.local_file_dict[title]
                    if last_modify <= exist_file.last_modify:
                        os.remove(real_path)
                        continue
                self.local_file_dict[title] = ProcessOnFile(None, title, last_modify)

    def login(self):
        """
        登录
        :return:
        """
        r = self.ss.post("https://www.processon.com/login",
                         {"login_email": self.user_name, "login_password": self.password})
        http_response_valid(r, 200)
        if "processon_userKey" not in self.ss.cookies.keys():
            logging.error("login failed")
            raise Exception()
        self.uk = self.ss.cookies["processon_userKey"]

    def get_online_file_list(self):
        """
        查询线上的文件列表，不包括 回收站
        :return:
        """
        load_data = {
            "resource": "diagrams",
            "folderId": "",
            "searchTitle": "",
            "sort": "",
            "view": "",
            "page": 1

        }
        r = self.ss.post("https://www.processon.com/folder/loadfiles",
                         headers={"content-type": "application/x-www-form-urlencoded"},
                         data=load_data)
        if http_response_valid(r, 200):
            js = r.json()
            if js["charts"]:
                for item in js["charts"]:
                    self.online_file_dict[item["title"]] = ProcessOnFile(item["chartId"], item["title"],
                                                                         item["lastModify"])
                return True
        return False

    def download(self, pof: ProcessOnFile):
        """
        下载线上的文件
        :param pof:type:ProcessOnFile
        :return:
        """
        r = self.ss.get("https://assets.processon.com/diagram_export?type=pos&chartId=%s&mind=" % pof.chartId,
                        stream=True)
        if not http_response_valid(r, 200):
            return False
        file_name = pof.title + file_name_split + pof.last_modify
        with open(os.path.join(self.path, file_name), 'wb') as f:
            for data in r.iter_content(chunk_size=1024):
                f.write(data)
        return True

    def to_trash(self, pof: ProcessOnFile):
        """
        删除到回收站
        :param pof
        :return:
        """
        r = self.ss.post("https://www.processon.com/folder/to_trash",
                         data={"fileId": pof.chartId, "fileType": "chart", "resource": ""},
                         headers={"content-type": "application/x-www-form-urlencoded"})
        return http_response_valid(r, 200)

    def trash_delete(self, pof: ProcessOnFile):
        """
        彻底删除
        :param pof:
        :return:
        """
        r = self.ss.post("https://www.processon.com/folder/remove_from_trash",
                         data={"fileId": pof.chartId, "fileType": "chart"},
                         headers={"content-type": "application/x-www-form-urlencoded"})
        return http_response_valid(r, 200)

    def file_import(self, file_path, file_name):
        """
        文件导入
        :param file_path: pos文件路径
        :param file_name: 文件名称
        :return:
        """
        fp = open(file_path)
        file_json = json.load(fp)
        fp.close()
        def_param = json.dumps(file_json["diagram"]["elements"])
        params = OrderedDict([("file_name", (None, file_name)),
                              ("file_type", (None, 'pos')),
                              ('def', (None, quote(def_param))),
                              ('team_id', (None, '')),
                              ('org_id', (None, '')),
                              ('folder', (None, 'root')),
                              ('category', (None, 'flow'))])
        r = self.ss.post("https://www.processon.com/import", files=params, allow_redirects=False)
        if http_response_valid(r, 303):
            location = r.headers["Location"]
            edit_url = "https://www.processon.com" + location
            logging.info("导入成功，编辑url: %s" % edit_url)

            return True
        return False

        # r = ss.get("https://www.processon.com" + location)
        # print(r.status_code)
        # file_id = parse_file_id(location)
        # client_time = int(time.time() * 1000)
        # r = ss.post("https://www.processon.com/diagraming/listen",
        #             data={"subject": file_id, "client": client_time})
        # uk = ss.cookies["processon_userKey"]
        # print(r.status_code)
        # print(r.request.url, r.request.body)
        # r = ss.get("https://cb.processon.com/diagraming/poll", params={"subject": file_id
        #     , "client": client_time, "uk": uk, "_": int(time.time() * 1000)})
        # print(r.status_code)
        # print(r.request.url, r.request.body)
        # r = ss.post("https://www.processon.com/diagraming/stop", data={"subject": file_id
        #     , "client": client_time, "uk": uk})
        # print(r.status_code)
        # print(r.request.url, r.request.body)

    def del_and_import(self, title):
        """
        导入文件，若文件达到配置上限，则下载和删除线上一个最早的文件
        倒入文件完成  删除本地文件
        :param title: 可以是文件路径  也可以是local list中的文件 title
        :return:
        """
        if os.path.exists(title):
            path = title
            file_name = os.path.splitext(os.path.basename(path))
        else:
            if title not in self.local_file_dict.keys():
                logging.warning("unknown file name")
                return
            file_vo = self.local_file_dict[title]
            file_name = file_vo.title
            path = os.path.join(self.path, file_vo.title + file_name_split + file_vo.last_modify)
        online_file_num = len(self.online_file_dict)

        if online_file_num >= self_file_max_num:
            online_files = self.online_file_dict.values()
            online_files = sorted(online_files, key=lambda x: x.last_modify, reverse=True)
            need_delete = online_files[0]
            logging.info("导入需删除文件为:%s" % need_delete.title)
            if not self.download(need_delete):
                logging.error("下载失败，终止导入")
                return
            if not self.delete_online(need_delete):
                logging.error("删除失败，终止导入")
                return
        if not self.file_import(path, file_name):
            logging.error("导入失败")
            return
        # 确认导入成功
        self.get_online_file_list()
        if file_name not in self.online_file_dict.keys():
            logging.error("请求成功，但是线上不存在")
            return
        self.refresh()

    def delete_online(self, pof: ProcessOnFile):
        """
        删除线上文件
        :param pof:
        :return:
        """
        if self.to_trash(pof):
            if self.trash_delete(pof):
                return True
            else:
                logging.error("回收站删除失败:%s" % pof.title)
        return False

    def download_del_all(self):
        """
        下载所有线上文件，并删除
        :return:
        """
        result = True
        for title, file in self.online_file_dict.items():
            logging.info("开始下载和删除文件:%s" % title)
            if not self.download(file):
                logging.error("download failed:%s" % title)
                result = False
                continue
            if not self.delete_online(file):
                logging.error("delete failed:%s" % title)
                result = False
                continue
            logging.info("已成功下载和删除:%s" % title)
        self.refresh()
        if not result:
            logging.error("部分下载或者删除失败")
        return result


def print_file(file_vo):
    print("%s\t%s" % (file_vo.title, file_vo.last_modify))


def cmd_man(cmd):
    print(cmd_dict.keys())


def cmd_list(cmd):
    args = cmd.split(' ')[1]
    if 'local' == args:
        for title, fileVo in p.local_file_dict.items():
            print_file(fileVo)
        return
    if 'online' == args:
        for title, fileVo in p.online_file_dict.items():
            print_file(fileVo)
        return
    print("unknown cmd")


def cmd_import(cmd):
    title = cmd.split(' ')[1]
    p.del_and_import(title)


def cmd_download(cmd):
    args = cmd.split(' ')[1]
    if 'all' == args:
        p.download_del_all()


cmd_dict = {
    "man": cmd_man,
    "list": cmd_list,
    "import": cmd_import,
    "download": cmd_download
}


def handle_command(cmd):
    cmd = cmd.strip()
    if cmd == '':
        return
    main_cmd = cmd.split(' ')[0]
    if main_cmd not in cmd_dict.keys():
        print('unknown cmd:%s' % main_cmd)
        return
    method = cmd_dict[main_cmd]
    method(cmd)


p = ProcessOn(user_name, password)

if __name__ == '__main__':
    while True:
        command = input("请输入命令:")
        try:
            handle_command(command)
        except Exception as e:
            logging.exception(command + " exec error")
