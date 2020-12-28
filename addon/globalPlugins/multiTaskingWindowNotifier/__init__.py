# -*- coding: utf-8 -*-
# multiTasking window notifier

#Copyright (C) 2020 dnz3d4c <advck1123 at gmail dot com>

#This file is covered by the GNU General Public License.
#See the file COPYING for more details.



import api
import globalPluginHandler
import globalVars
import tones
import scriptHandler
from scriptHandler import script
import os
import wx
import ui



class GlobalPlugin(globalPluginHandler.GlobalPlugin):

	# 추가 기능 기본 변수
	configPath = globalVars.appArgs.configPath
	global APPListFile
	APPListFile = os.path.join(configPath, "addons", "multiTaskingWindowNotifier", "globalPlugins", "multiTaskingWindowNotifier") + "\\app.list"
	global APPList
	APPList = []

	def __init__(self):
		super(GlobalPlugin, self).__init__()
		with open(APPListFile, "r", encoding="utf8") as f:
			global APPList
			APPList = f.readlines()

	# 창 목록 추가를 위한 제스처/함수
	@script(
	description = _("창 목록에 창 제목을 추가합니다"),
	category = ("multiTaskingWindowNotifier"),
	gesture = ("kb:NVDA+Shift+t")
	)

	def script_addListWindow(self, gesture):
		with open(APPListFile, "r+", encoding="utf8") as f:
			global APPList
			APPList = f.readlines()
			for i in range(len(APPList)):
				text = APPList[i].strip("\n")
				fg = api.getForegroundObject()
				if fg.name == text:
					ui.message("이미 추가된 항목입니다.")

	def event_gainFocus (self, obj, nextHandler):
		obj = api.getFocusObject()
		if obj.windowClassName == "MultitaskingViewFrame":
			# 앱 목록에서 각 항목의 \N문자 제거
			global APPList
			for i in range(len(APPList)):
				text = APPList[i].strip("\n")
				# 앱 항목과 초점 객체가 일치하면 앱 항목에 해당하는 비프음 출력
				if obj.name == text:
					beepList = [
					262 , 294, 330, 349, 392, 440, 494,
					523 , 587, 659, 699, 784, 880, 988, 1047
					]
					tones.beep(beepList[i], 100, 30, 30)
		nextHandler()
