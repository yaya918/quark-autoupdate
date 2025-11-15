#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
夸克资源搜索与添加接口（异步版本）
功能：接收资源名称，立即返回响应，后台处理资源添加
"""
import os
import sys
import json
import time
import uuid
import threading
import re
import requests
import argparse
from flask import Flask, request, jsonify
from quark_failed_task_update import FailedTaskIncrementalUpdater

app = Flask(__name__)

# 全局任务存储
task_status = {}


class AsyncResourceSearchAPI:
    def __init__(self, config_path):
        self.config_path = config_path
        self.updater = FailedTaskIncrementalUpdater(config_path)
        self.updater.load_config()

        # 从环境变量获取配置
        self.api_token = os.getenv('QUARK_API_TOKEN', '87e7eb745cb0d5d8')
        self.base_url = os.getenv('QUARK_BASE_URL', 'http://192.168.2.99:15005')

    def clean_taskname(self, taskname):
        """清理任务名称，去除空格、换行等特殊字符"""
        if not taskname:
            return taskname

        # 去除首尾空白字符
        cleaned = taskname.strip()

        # 替换多种空白字符为单个空格
        cleaned = re.sub(r'\s+', ' ', cleaned)

        # 去除可能存在的特殊控制字符
        cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', cleaned)

        print(f"🔧 任务名称清理: '{taskname}' -> '{cleaned}'")
        return cleaned

    def trigger_resource_update(self):
        """触发资源更新脚本"""
        try:
            url = f"{self.base_url}/run_script_now?token={self.api_token}"
            headers = {
                "Content-Type": "application/json"
            }

            print("🔄 触发资源更新脚本...")
            response = requests.post(url, json={}, headers=headers, timeout=30)

            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    print("✅ 资源更新脚本触发成功")
                    return True
                else:
                    print(f"❌ 资源更新脚本返回错误: {result.get('message', '未知错误')}")
                    return False
            else:
                print(f"❌ 资源更新脚本请求失败，状态码: {response.status_code}")
                return False

        except requests.exceptions.Timeout:
            print("❌ 资源更新脚本请求超时")
            return False
        except Exception as e:
            print(f"❌ 触发资源更新脚本时出错: {e}")
            return False

    def background_add_resource(self, task_id, taskname, savepath=None, runweek=None, pattern="", replace=""):
        """后台添加资源的线程函数"""
        try:
            # 清理任务名称
            cleaned_taskname = self.clean_taskname(taskname)

            task_status[task_id] = {
                'status': 'processing',
                'message': f'正在搜索资源: {cleaned_taskname}',
                'progress': 10
            }

            # 检查任务是否已存在
            existing_tasks = [task for task in self.updater.config_data.get('tasklist', [])
                              if task.get('taskname') == cleaned_taskname]
            if existing_tasks:
                task_status[task_id] = {
                    'status': 'exists',
                    'message': f'任务 "{cleaned_taskname}" 已存在',
                    'taskname': cleaned_taskname
                }
                return

            task_status[task_id] = {
                'status': 'processing',
                'message': f'正在获取资源列表: {cleaned_taskname}',
                'progress': 30
            }

            # 获取新的资源列表（使用清理后的任务名）
            new_resources = self.updater.get_new_resources(cleaned_taskname)
            if not new_resources:
                task_status[task_id] = {
                    'status': 'not_found',
                    'message': f'未找到资源: {cleaned_taskname}',
                    'taskname': cleaned_taskname
                }
                return

            task_status[task_id] = {
                'status': 'processing',
                'message': f'分析匹配资源: {cleaned_taskname}',
                'progress': 50
            }

            # 过滤匹配的任务名
            matched_resources = []
            for resource in new_resources:
                candidate_taskname = resource.get('taskname', '')
                if candidate_taskname and self.updater.is_taskname_match(candidate_taskname, cleaned_taskname):
                    matched_resources.append(resource)

            if not matched_resources:
                task_status[task_id] = {
                    'status': 'no_match',
                    'message': f'未找到任务名匹配的资源: {cleaned_taskname}',
                    'taskname': cleaned_taskname
                }
                return

            task_status[task_id] = {
                'status': 'processing',
                'message': f'分析资源结构: {len(matched_resources)}个匹配资源',
                'progress': 70
            }

            # 分析候选资源 - 使用优化版分析方法
            resources_analysis = []
            for i, resource in enumerate(matched_resources[:3]):  # 只分析前3个
                new_url = resource.get('shareurl')
                new_taskname = resource.get('taskname', '未知资源')

                if not new_url:
                    continue

                task_status[task_id] = {
                    'status': 'processing',
                    'message': f'分析资源 {i + 1}/{min(3, len(matched_resources))}: {new_taskname}',
                    'progress': 70 + (i * 10)
                }

                # 使用优化版资源结构分析方法
                analysis = self.updater.analyze_resource_structure_optimized(new_url, cleaned_taskname)
                resources_analysis.append(analysis)
                time.sleep(1)  # 稍微增加延迟避免请求过快

            task_status[task_id] = {
                'status': 'processing',
                'message': f'选择最佳资源',
                'progress': 90
            }

            # 选择最佳资源（没有已保存剧集，所以传入空列表）
            best_resource = self.updater.select_best_resource(resources_analysis, cleaned_taskname, [])

            if not best_resource:
                task_status[task_id] = {
                    'status': 'no_suitable',
                    'message': f'未找到合适的资源: {cleaned_taskname}',
                    'taskname': cleaned_taskname
                }
                return

            # 生成默认保存路径（使用清理后的任务名）
            if not savepath:
                savepath = f"/qh_nas/Movie/{cleaned_taskname}"

            # 设置默认运行周期
            if not runweek:
                runweek = [1, 2, 3, 4, 5, 6, 7]  # 每天运行

            # 创建新任务配置（使用清理后的任务名）
            new_task = {
                "taskname": cleaned_taskname,
                "shareurl": best_resource['url'],
                "savepath": savepath,
                "pattern": pattern,
                "replace": replace,
                "enddate": "",  # 无结束日期
                "emby_id": "",
                "update_subdir": "",
                "runweek": runweek,
                "ignore_extension": False,
                "media_id": "",
                "addition": {
                    "emby": {
                        "media_id": "",
                        "try_match": True
                    },
                    "alist_strm_gen": {
                        "auto_gen": True
                    },
                    "aria2": {
                        "auto_download": False,
                        "pause": False
                    },
                    "alist_sync": {
                        "enable": False,
                        "save_path": "",
                        "verify_path": "",
                        "full_path_mode": False
                    },
                    "smartstrm": {},
                    "fnv": {
                        "auto_refresh": False,
                        "mdb_name": ""
                    }
                },
                "last_updated": time.strftime("%Y-%m-%dT%H:%M:%S")
            }

            # 如果有最佳文件夹信息，使用最佳文件夹的分享链接和起始fid
            if best_resource.get('best_folder'):
                best_folder = best_resource['best_folder']
                new_task['shareurl'] = best_folder['share_url']

                # 使用最佳文件夹中的第一个剧集作为起始点
                if best_folder.get('episodes'):
                    first_episode = min(best_folder['episodes'], key=lambda x: x['episode'])
                    new_task['startfid'] = first_episode['fid']

                    # 记录文件夹信息
                    new_task['best_folder_info'] = {
                        'folder_path': [item.get('file_name', '') for item in best_folder['folder_path']],
                        'min_episode': best_folder['min_episode'],
                        'max_episode': best_folder['max_episode'],
                        'episode_count': len(best_folder['episodes'])
                    }

            # 添加到配置
            if 'tasklist' not in self.updater.config_data:
                self.updater.config_data['tasklist'] = []

            self.updater.config_data['tasklist'].append(new_task)

            # 保存配置
            if self.updater.save_config():
                episode_info = ""
                if best_resource.get('all_episodes'):
                    min_ep = best_resource.get('min_episode', '?')
                    max_ep = best_resource.get('max_episode', '?')
                    episode_info = f"，共{len(best_resource['all_episodes'])}集，从第{min_ep}到第{max_ep}集"

                # 如果有最佳文件夹信息，添加文件夹详情
                folder_info = ""
                if best_resource.get('best_folder'):
                    folder_path = "/".join(
                        [item.get('file_name', '') for item in best_resource['best_folder']['folder_path']]) or "根目录"
                    folder_info = f"，最佳文件夹: {folder_path}"

                task_status[task_id] = {
                    'status': 'success',
                    'message': f'成功添加"{cleaned_taskname}"{episode_info}{folder_info}',
                    'taskname': cleaned_taskname,
                    'task': new_task,
                    'episodes': len(best_resource.get('all_episodes', [])),
                    'min_episode': best_resource.get('min_episode'),
                    'max_episode': best_resource.get('max_episode'),
                    'best_folder': best_resource.get('best_folder') is not None
                }

                # 成功添加资源后触发资源更新
                print("🔄 新资源添加成功，触发资源更新...")
                update_triggered = self.trigger_resource_update()
                if update_triggered:
                    task_status[task_id]['update_triggered'] = True
                    task_status[task_id]['message'] += "，已触发资源更新"
                else:
                    task_status[task_id]['update_triggered'] = False
                    task_status[task_id]['message'] += "，资源更新触发失败"

            else:
                task_status[task_id] = {
                    'status': 'save_error',
                    'message': '配置保存失败',
                    'taskname': cleaned_taskname
                }

        except Exception as e:
            task_status[task_id] = {
                'status': 'error',
                'message': f'处理过程中出错: {str(e)}',
                'taskname': cleaned_taskname
            }

    def async_add_resource(self, taskname, savepath=None, runweek=None, pattern="", replace=""):
        """异步添加资源"""
        # 清理任务名称
        cleaned_taskname = self.clean_taskname(taskname)

        task_id = str(uuid.uuid4())

        # 立即返回任务ID
        task_status[task_id] = {
            'status': 'accepted',
            'message': f'已开始处理资源添加: {cleaned_taskname}',
            'task_id': task_id,
            'taskname': cleaned_taskname,
            'original_taskname': taskname  # 保留原始名称用于参考
        }

        # 在后台线程中处理
        thread = threading.Thread(
            target=self.background_add_resource,
            args=(task_id, cleaned_taskname, savepath, runweek, pattern, replace)
        )
        thread.daemon = True
        thread.start()

        return task_id

    def search_resources(self, taskname, limit=5):
        """只搜索资源，不添加到配置"""
        try:
            # 清理任务名称
            cleaned_taskname = self.clean_taskname(taskname)
            print(f"🔍 正在搜索资源: {cleaned_taskname}")

            new_resources = self.updater.get_new_resources(cleaned_taskname)
            if not new_resources:
                return {
                    'success': False,
                    'message': f'未找到资源: {cleaned_taskname}'
                }

            # 过滤匹配的任务名
            matched_resources = []
            for resource in new_resources:
                candidate_taskname = resource.get('taskname', '')
                if candidate_taskname and self.updater.is_taskname_match(candidate_taskname, cleaned_taskname):
                    matched_resources.append(resource)

            if not matched_resources:
                return {
                    'success': False,
                    'message': f'未找到任务名匹配的资源: {cleaned_taskname}'
                }

            # 返回搜索结果
            result_resources = []
            for resource in matched_resources[:limit]:
                result_resources.append({
                    'taskname': resource.get('taskname'),
                    'shareurl': resource.get('shareurl'),
                    'source': resource.get('source', 'unknown')
                })

            return {
                'success': True,
                'message': f'找到 {len(result_resources)} 个匹配资源',
                'resources': result_resources
            }

        except Exception as e:
            return {
                'success': False,
                'message': f'搜索过程中出错: {str(e)}'
            }


# 全局API实例
api_instance = None


@app.route('/api/search', methods=['GET'])
def search_resources():
    """搜索资源接口"""
    taskname = request.args.get('taskname')
    limit = int(request.args.get('limit', 5))

    if not taskname:
        return jsonify({
            'success': False,
            'message': '缺少 taskname 参数'
        }), 400

    result = api_instance.search_resources(taskname, limit)
    return jsonify(result)


@app.route('/api/add', methods=['POST'])
def add_resource():
    """添加资源到配置接口（异步版本）"""
    data = request.json
    taskname = data.get('taskname')
    savepath = data.get('savepath')
    runweek = data.get('runweek', [1, 2, 3, 4, 5, 6, 7])
    pattern = data.get('pattern', '')
    replace = data.get('replace', '')

    if not taskname:
        return jsonify({
            'success': False,
            'message': '缺少 taskname 参数'
        }), 400

    # 异步处理，立即返回任务ID
    task_id = api_instance.async_add_resource(taskname, savepath, runweek, pattern, replace)

    # 获取清理后的任务名
    cleaned_taskname = api_instance.clean_taskname(taskname)

    return jsonify({
        'success': True,
        'message': '已开始处理资源添加请求',
        'task_id': task_id,
        'taskname': cleaned_taskname,
        'original_taskname': taskname,  # 返回原始名称
        'status_url': f'/api/task/{task_id}'
    })


@app.route('/api/add_simple', methods=['GET'])
def add_resource_simple():
    """简化版添加资源接口（GET请求，适合快捷指令）"""
    taskname = request.args.get('taskname')
    savepath = request.args.get('savepath')

    if not taskname:
        return jsonify({
            'success': False,
            'message': '缺少 taskname 参数'
        }), 400

    # 异步处理，立即返回任务ID
    task_id = api_instance.async_add_resource(taskname, savepath)

    # 获取清理后的任务名
    cleaned_taskname = api_instance.clean_taskname(taskname)

    return jsonify({
        'success': True,
        'message': '已开始处理资源添加请求',
        'task_id': task_id,
        'taskname': cleaned_taskname,
        'original_taskname': taskname,
        'status_url': f'/api/task/{task_id}'
    })


@app.route('/api/task/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """获取任务状态接口"""
    if task_id not in task_status:
        return jsonify({
            'success': False,
            'message': '任务ID不存在'
        }), 404

    status_info = task_status[task_id]
    return jsonify({
        'success': True,
        'task_id': task_id,
        **status_info
    })


@app.route('/api/tasks', methods=['GET'])
def list_tasks():
    """获取任务列表接口"""
    try:
        tasks = api_instance.updater.config_data.get('tasklist', [])
        return jsonify({
            'success': True,
            'tasks': tasks,
            'count': len(tasks)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取任务列表失败: {str(e)}'
        }), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return jsonify({
        'success': True,
        'message': '服务运行正常',
        'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
        'active_tasks': len([t for t in task_status.values() if t.get('status') == 'processing'])
    })


@app.route('/api/trigger_update', methods=['POST'])
def trigger_update():
    """手动触发资源更新接口"""
    try:
        result = api_instance.trigger_resource_update()
        return jsonify({
            'success': result,
            'message': '资源更新脚本触发成功' if result else '资源更新脚本触发失败'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'触发资源更新时出错: {str(e)}'
        }), 500


@app.route('/api/cleanup', methods=['POST'])
def cleanup_tasks():
    """清理已完成的任务状态（可选）"""
    global task_status

    # 保留最近100个任务，清理更早的已完成任务
    current_time = time.time()
    task_ids_to_remove = []

    # 按任务ID排序，保留最新的
    all_task_ids = sorted(task_status.keys())
    if len(all_task_ids) > 100:
        # 保留最新的100个
        task_ids_to_remove = all_task_ids[:-100]

    # 额外清理24小时前的已完成任务
    for task_id in list(task_status.keys()):
        if task_id in task_ids_to_remove:
            continue

        task_info = task_status[task_id]
        if task_info.get('status') in ['success', 'error', 'exists', 'not_found', 'no_match', 'no_suitable',
                                       'save_error']:
            # 这里可以添加时间检查逻辑，如果需要的话
            if len(all_task_ids) <= 100:  # 如果总数不多，不清除
                continue
            task_ids_to_remove.append(task_id)

    for task_id in task_ids_to_remove:
        del task_status[task_id]

    return jsonify({
        'success': True,
        'message': f'已清理 {len(task_ids_to_remove)} 个任务状态',
        'remaining_tasks': len(task_status)
    })


def main():
    """主函数"""
    global api_instance

    parser = argparse.ArgumentParser(description='夸克资源搜索与添加API（异步版本）')
    parser.add_argument('--config', default='quark_config.json', help='配置文件路径')
    parser.add_argument('--host', default='0.0.0.0', help='监听地址')
    parser.add_argument('--port', type=int, default=5001, help='监听端口')

    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"❌ 配置文件不存在: {args.config}")
        sys.exit(1)

    try:
        # 初始化API
        api_instance = AsyncResourceSearchAPI(args.config)
        print(f"✅ API服务初始化成功（异步版本）")
        print(f"📁 配置文件: {args.config}")
        print(f"🌐 服务地址: http://{args.host}:{args.port}")
        print(f"🔄 异步接口: POST /api/add 或 GET /api/add_simple?taskname=资源名")
        print(f"📊 状态查询: GET /api/task/<task_id>")
        print(f"🚀 资源更新: POST /api/trigger_update")

        # 启动Flask应用
        app.run(host=args.host, port=args.port, debug=False)

    except Exception as e:
        print(f"❌ API服务启动失败: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()