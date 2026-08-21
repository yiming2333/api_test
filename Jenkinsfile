import groovy.json.JsonOutput

pipeline {
    agent any

    options {
        timeout(time: params?.MARK == 'regression' ? 60 : 30, unit: 'MINUTES')
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '30'))
    }

    parameters {
        choice(name: 'ENV',            choices: ['dev', 'prod'],                 description: '选择运行环境')
        choice(name: 'MARK',           choices: ['all', 'smoke', 'regression'],  description: '选择用例标记')
        string(name: 'RERUNS',         defaultValue: '3',                        description: '失败重试次数')
        string(name: 'RERUNS_DELAY',   defaultValue: '1',                        description: '失败重试间隔（秒）')
        choice(name: 'PARALLEL',       choices: ['off', 'auto', '2', '3','4','5', '10'], description: '并发模式: off=串行, auto=自动检测CPU核心数, 数字=指定worker数')
    }

    environment {
        PYTHON_PATH        = 'C:/Users/27088/AppData/Local/Programs/Python/Python310/python.exe'
        PIP_INDEX_URL      = 'https://pypi.tuna.tsinghua.edu.cn/simple'
        ALLURE_RESULTS     = 'reports/allure-results'
        ALLURE_REPORT_NAME = 'AllureReport'
        MAIL_RECIPIENT     = 'yiming_2333@sina.com'
        PYTHONIOENCODING   = 'utf-8'
        GIT_URL            = 'https://github.com/yiming2333/api_test.git'
        GIT_BRANCH         = 'master'
        GIT_CREDENTIALS_ID = ''
        REPORT_LINK        = "${env.JENKINS_URL}job/${env.JOB_NAME}/${env.BUILD_NUMBER}/allure/"

        // ========== 钉钉配置 ==========
        // ★ P0安全优化(1)：Webhook Token 不再硬编码，从 Jenkins Credentials 读取
        //   使用前请在 Jenkins 后台创建凭证：
        //   类型：Secret text → ID 填 dingtalk_webhook → Secret 粘贴钉钉 Webhook 的完整 URL
        DINGTALK_WEBHOOK   = credentials('dingtalk_webhook')
        DINGTALK_KEYWORD   = '测试'
    }

    stages {
        // ====================================================================
        //  🧾 阶段1：信息采集与准备工作
        // ====================================================================
        stage('🧾 1. 信息采集 & 准备') {
            stages {

                // P2 优化(11)：先清理工作区，消除上次构建的"幽灵文件"
                stage('1.1 🧹 清理工作区') {
                    steps {
                        echo "清理 __pycache__ / .pytest_cache / 旧报告 / 旧日志 ..."
                        bat '''
                            @echo off
                            chcp 65001 >nul
                            if exist "__pycache__"   rmdir /s /q __pycache__
                            if exist ".pytest_cache" rmdir /s /q .pytest_cache
                            if exist "reports"      rmdir /s /q reports
                            if exist "diagnostics"  rmdir /s /q diagnostics
                            if exist "logs"         ( del /q logs\\*.log 2>nul & echo logs 已清理 )
                            echo ✅ 工作区清理完成
                        '''
                    }
                }

                // 原 stage 0：获取构建用户
                stage('1.2 👤 获取构建用户') {
                    steps {
                        script {
                            try {
                                wrap([$class: 'BuildUser']) {
                                    env.TRIGGER_USER = env.BUILD_USER_ID ?: '未知(插件未生效)'
                                }
                            } catch (e) {
                                echo "⚠️ 无法获取构建用户: ${e.message}"
                                env.TRIGGER_USER = '未知'
                            }
                            echo "本次构建触发人: ${env.TRIGGER_USER}"
                        }
                    }
                }

                // 原 stage 1：拉取代码 + P0 优化(3) 凭证日志提示
                stage('1.3 📥 拉取代码') {
                    options { retry(3) }
                    steps {
                        echo "正在从 Git 拉取代码 (${env.GIT_BRANCH})..."
                        script {
                            def gitConfig = [branch: env.GIT_BRANCH, url: env.GIT_URL]
                            if (env.GIT_CREDENTIALS_ID?.trim()) {
                                gitConfig.credentialsId = env.GIT_CREDENTIALS_ID
                                echo "✅ 使用 Git 凭证: ${env.GIT_CREDENTIALS_ID}"
                            } else {
                                echo "⚠️ 未配置 GIT_CREDENTIALS_ID，假设仓库为公开仓库。若拉取失败请在 environment 中配置凭证ID。"
                            }
                            git gitConfig
                        }
                    }
                }

                // 原 stage 2：安装依赖 + P1 优化(5) retry/timeout/Python检查
                stage('1.4 🧪 安装 Python 依赖') {
                    options {
                        retry(count: 3)
                        timeout(time: 10, unit: 'MINUTES')
                    }
                    steps {
                        echo "正在安装 Python 依赖..."
                        script {
                            // P1 优化(5)：先确认 Python 解释器存在，不然 pip 一步直接炸一堆看不懂的错
                            def pyStatus = bat(
                                script: """
                                    @echo off
                                    chcp 65001 >nul
                                    "${PYTHON_PATH}" --version
                                """,
                                returnStatus: true
                            )
                            if (pyStatus != 0) {
                                error("❌ Python 解释器不存在或无法执行: ${PYTHON_PATH}\\n请在 Jenkins 管理页修改 environment.PYTHON_PATH")
                            }

                            // P1 优化(4)：用 pythonCmd() 统一执行
                            bat script: pythonCmd('-m pip', "install -r requirements.txt -q -i ${PIP_INDEX_URL} --cache-dir .pip-cache")
                        }
                    }
                }
            }
        }

        // ====================================================================
        //  🚀 阶段2：Mock 服务 & 数据重置（仅 dev 环境）
        // ====================================================================
        stage('🚀 2. Mock 与数据重置') {
            when { expression { params.ENV == 'dev' } }
            stages {

                // 原 stage 2.5 + P1 优化(6) 健康检查
                stage('2.1 🎬 启动 Mock 服务') {
                    steps {
                        echo "探测 Mock 服务，未运行则自动启动..."
                        bat script: pythonCmd('scripts/ensure_mock.py', "start --env ${params.ENV}")

                        // P1 优化(6)：健康检查 —— 复用 ensure_mock status（exit 0=Mock在跑），确认 Mock 真的"活了"再往下走
                        echo "⏳ 等待 Mock 服务就绪（探测 127.0.0.1:5000，最多30秒）..."
                        script {
                            timeout(time: 30, unit: 'SECONDS') {
                                waitUntil(initialRecurrencePeriod: 2000) {
                                    def pingOk = bat(
                                        script: pythonCmd('scripts/ensure_mock.py', "status --env ${params.ENV}"),
                                        returnStatus: true
                                    )
                                    return pingOk == 0
                                }
                                echo "✅ Mock 服务就绪（端口 5000 正常响应）"
                            }
                        }
                    }
                }

                // 原 stage 2.6 + P0 优化(2) 失败直接终止
                stage('2.2 🗑️ 重置测试数据') {
                    steps {
                        echo "清理上一次可能残留的业务数据（orders/projects/tasks/file_uploads）..."
                        script {
                            def resetExitCode = bat(
                                script: pythonCmd('scripts/ensure_mock.py', "reset-db --env ${params.ENV}"),
                                returnStatus: true
                            )
                            // P0 优化(2)：重置失败 = 拒绝跑测试，防止在脏数据上产生假阳性/假阴性
                            if (resetExitCode != 0) {
                                error("❌ 数据库重置失败（exit=${resetExitCode}）！\\n拒绝在脏数据上执行测试，请检查 ensure_mock.py 日志 / DB 连接配置。")
                            }
                            echo "✅ DB 重置完成，所有业务表已清空"
                        }
                    }
                }
            }
        }

        // ====================================================================
        //  ⚙️ 阶段3：执行测试
        // ====================================================================
        stage('⚙️ 3. 执行测试 & 写环境信息') {
            stages {

                // 原 stage 3：执行 Pytest
                stage('3.1 🧪 执行 Pytest 测试') {
                    steps {
                        echo "开始执行 Pytest 测试 (MARK=${params.MARK}, PARALLEL=${params.PARALLEL}, RERUNS=${params.RERUNS})..."
                        script {
                            catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                                // 拼接 mark 参数
                                def markArg = params.MARK != 'all' ? "-m ${params.MARK}" : ""

                                // 根据用户选择拼接 xdist 参数
                                def xdistArg = ''
                                switch (params.PARALLEL) {
                                    case 'off':
                                        xdistArg = ''
                                        echo "📌 执行模式: 串行（单 worker）"
                                        break
                                    case 'auto':
                                        xdistArg = '-n auto'
                                        echo "📌 执行模式: auto（自动检测 CPU 核心数）"
                                        break
                                    default:
                                        xdistArg = "-n ${params.PARALLEL}"
                                        echo "📌 执行模式: 指定 ${params.PARALLEL} 个并发 workers"
                                        break
                                }

                                bat script: pythonCmd('-m pytest', """${markArg} ${xdistArg} ^
                                    --env=${params.ENV} ^
                                    --alluredir=${ALLURE_RESULTS} ^
                                    --clean-alluredir ^
                                    --reruns ${params.RERUNS} ^
                                    --reruns-delay ${params.RERUNS_DELAY} ^
                                    -v""")
                            }
                        }
                    }
                }

                // 原 stage 3.5：写入 Allure 环境信息 & 执行器信息
                stage('3.2 📝 写入 Allure 环境 & 执行器信息') {
                    steps {
                        script {
                            // environment.properties
                            def envProps = """
                                Environment=${params.ENV}
                                Python.Version=3.10
                                Pytest.Mark=${params.MARK}
                                Parallel.Mode=${params.PARALLEL}
                                Retry.Count=${params.RERUNS}
                                Trigger.User=${env.TRIGGER_USER ?: 'unknown'}
                                Build.Number=${env.BUILD_NUMBER}
                                Git.Branch=${env.GIT_BRANCH}
                                Base.URL=${getBaseUrl(params.ENV)}
                                OS=Windows
                            """.stripIndent().trim()
                            writeFile file: "${ALLURE_RESULTS}/environment.properties", text: envProps, encoding: 'UTF-8'
                            echo "✅ environment.properties 已写入"

                            // executor.json
                            def executorData = [
                                name       : 'Jenkins',
                                type       : 'jenkins',
                                url        : env.JENKINS_URL,
                                buildOrder : env.BUILD_NUMBER.toInteger(),
                                buildName  : "#${env.BUILD_NUMBER}",
                                buildUrl   : "${env.JENKINS_URL}job/${env.JOB_NAME}/${env.BUILD_NUMBER}/",
                                reportUrl  : "${REPORT_LINK}",
                                reportName : ALLURE_REPORT_NAME
                            ]
                            def jsonStr = JsonOutput.toJson(executorData)
                            writeFile file: "${ALLURE_RESULTS}/executor.json", text: jsonStr, encoding: 'UTF-8'
                            echo "✅ executor.json 已写入"
                        }
                    }
                }
            }
        }

        // ====================================================================
        //  📊 阶段4：生成 Allure 报告
        // ====================================================================
        stage('📊 4. 生成 Allure 报告') {
            steps {
                echo "生成 Allure 测试报告..."
                allure includeProperties: false,
                       jdk: '',
                       results: [[path: 'reports/allure-results']],
                       reportBuildPolicy: 'ALWAYS'
            }
        }
    }

    // ====================================================================
    //  收尾：善后工作（无论成功/失败都执行）
    // ====================================================================
    post {
        always {
            echo "========== 🧹 流水线收尾：清理资源 =========="

            script {
                // ---- dev 环境显式停止 Mock 服务 ----
                if (params.ENV == 'dev') {
                    catchError(buildResult: null, stageResult: null, message: "停止 Mock 失败但不影响构建结果") {
                        bat script: pythonCmd('scripts/ensure_mock.py', "stop --env ${params.ENV}")
                        echo "✅ Mock 服务已停止"
                    }
                }

                // ---- P2 优化(10)：构建耗时大盘点 ----
                def totalMs  = currentBuild.duration       // Jenkins 已提供毫秒
                def totalMin = (totalMs / 60000) as int
                def totalSec = ((totalMs % 60000) / 1000) as int
                echo """
╔══════════════════════════════════════════════════════════╗
║  🕐 本次构建总耗时：${totalMin}分${totalSec}秒
║  🎯 构建结果：${currentBuild.currentResult}
║  👤 触发人员：${env.TRIGGER_USER ?: '未知'}
║  🔧 运行环境：${params.ENV}  |  MARK=${params.MARK}  |  并发=${params.PARALLEL}
║  📊 详细耗时图表请打开 Blue Ocean / 各 Stage 日志查看
╚══════════════════════════════════════════════════════════╝
""".stripIndent()

                // ---- 归档日志 ----
                archiveArtifacts artifacts: 'logs/*.log', allowEmptyArchive: true
            }
        }

        success {
            echo "========== ✅ 所有测试用例通过！ =========="
            script { notifyAll('SUCCESS', 'green', '✅') }
        }

        failure {
            echo "========== ❌ 存在失败的测试用例 =========="
            script {
                // ---- P2 优化(8)：失败时收集诊断信息归档 ----
                catchError(buildResult: null, stageResult: null, message: "诊断信息收集失败，跳过") {
                    echo "📦 收集失败现场诊断信息..."
                    bat script: 'if not exist "diagnostics" mkdir diagnostics'
                    // 1) 抓 DB 当前数据量快照：先打印到日志（方便直接看），再用bat重定向写入归档文件
                    if (params.ENV == 'dev') {
                        bat script: pythonCmd('scripts/ensure_mock.py', "db-status --env ${params.ENV}")
                        bat script: pythonCmd('scripts/ensure_mock.py', "db-status --env ${params.ENV} > diagnostics\\db_status.txt 2>&1")
                    }
                    // 2) 复制 mock 日志 + pytest 日志
                    bat '''
                        @echo off
                        chcp 65001 >nul
                        if exist "logs" (
                            copy /Y logs\\*.log diagnostics\\ >nul
                            echo ✅ 日志已复制到 diagnostics/
                        ) else ( echo ⚠️ 没有 logs 目录 )
                    '''
                    // 3) 归档
                    archiveArtifacts artifacts: 'diagnostics/**/*', allowEmptyArchive: true
                    echo "✅ 诊断信息已归档到 Jenkins Artifacts（diagnostics/ 目录）"
                }

                // ---- 通知失败 ----
                notifyAll('FAILURE', 'red', '❌')
            }
        }
    }
}

// ================================================================
//  P1 优化(4)：统一的 Python 命令执行封装
//    自动处理 chcp 65001（中文不乱码） + PYTHON_PATH 拼接
//    之前写了 N 遍 "chcp 65001  ${PYTHON_PATH}"，现在一个函数搞定
// ================================================================
def pythonCmd(String pyArgs, String extraArgs = '') {
    return """
        @echo off
        chcp 65001 >nul
        "${env.PYTHON_PATH}" ${pyArgs} ${extraArgs}
    """.stripIndent().trim()
}

// ================================================================
//  统一通知入口：邮件 + 钉钉，后续加渠道只改这一个函数
// ================================================================
def notifyAll(String status, String color, String icon) {
    // 邮件通知
    try {
        sendEmailNotification(status, color, icon)
    } catch (e) {
        echo "⚠️ 邮件发送失败: ${e.message}"
    }

    // 钉钉通知
    try {
        sendDingTalkNotification(status, icon)
    } catch (e) {
        echo "⚠️ 钉钉发送失败: ${e.message}"
    }
}

// ================================================================
//  根据环境参数返回 base_url（读取 config/config.yaml）
//  ★ 注意：Windows CMD 下 python -c 后面必须用双引号包裹整段代码！
//          否则空格会被拆成多个参数，Python 只收到第一个单词就报错
// ================================================================
def getBaseUrl(String envName) {
    def output = bat(
        script: """
            @echo off
            chcp 65001 >nul
            "${env.PYTHON_PATH}" -c "from common.yaml_handler import get_config; print(get_config('${envName}')['base_url'])"
        """.stripIndent().trim(),
        returnStdout: true
    ).trim()
    return output.readLines().last()
}

// ================================================================
//  邮件通知
// ================================================================
def sendEmailNotification(String status, String color, String icon) {
    emailext(
        to      : env.MAIL_RECIPIENT,
        subject : "${icon} 测试${status == 'SUCCESS' ? '通过' : '失败'} - ${env.JOB_NAME} - Build #${env.BUILD_NUMBER}",
        body    : """
            <p>各位同事，大家好！</p>
            <p>项目 <strong>${env.JOB_NAME}</strong> 构建${status == 'SUCCESS' ? '成功' : '失败'}！</p>
            <ul>
                <li>构建编号：<strong>#${env.BUILD_NUMBER}</strong></li>
                <li>构建状态：<span style="color: ${color};">${icon} ${status}</span></li>
                <li>触发人：${env.TRIGGER_USER ?: '未知'}</li>
                <li>并发模式：${params.PARALLEL}</li>
                <li>重试次数：${params.RERUNS}</li>
                <li>测试报告：<a href="${env.REPORT_LINK}">${env.REPORT_LINK}</a></li>
            </ul>
            <p>请点击上方链接查看 Allure 测试报告详情。</p>
            <hr/>
            <p style="font-size: 12px; color: gray;">此邮件由 Jenkins 自动发送，请勿回复。</p>
        """,
        mimeType: 'text/html'
    )
}

// ================================================================
//  钉钉机器人通知
// ================================================================
def sendDingTalkNotification(String status, String icon) {
    def keyword = env.DINGTALK_KEYWORD
    def titleText = "${keyword}${icon} Jenkins ${status == 'SUCCESS' ? '构建成功 ✅' : '构建失败 ❌'}"

    def text = """### ${titleText}

- **项目**: ${env.JOB_NAME}
- **构建号**: #${env.BUILD_NUMBER}
- **环境**: ${params.ENV}
- **并发模式**: ${params.PARALLEL}
- **重试次数**: ${params.RERUNS}
- **触发人**: ${env.TRIGGER_USER ?: '未知'}
- **[📊 查看测试报告](${env.REPORT_LINK})**
""".trim()

    def payload = JsonOutput.toJson([
        msgtype : 'markdown',
        markdown: [title: titleText, text: text]
    ])

    httpRequest(
        url              : env.DINGTALK_WEBHOOK,
        httpMode         : 'POST',
        contentType      : 'APPLICATION_JSON',
        requestBody      : payload,
        validResponseCodes: '200',
        quiet            : true
    )
}
