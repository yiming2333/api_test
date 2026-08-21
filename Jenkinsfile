import groovy.json.JsonOutput

pipeline {
    agent any

    options {
        timeout(time: params?.MARK == 'regression' ? 60 : 30, unit: 'MINUTES')
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '30'))
    }

    parameters {
        choice(name: 'ENV',      choices: ['dev', 'prod'],                description: '选择运行环境')
        choice(name: 'MARK',     choices: ['all', 'smoke', 'regression'], description: '选择用例标记')
        string(name: 'RERUNS',   defaultValue: '3',                       description: '失败重试次数')
        string(name: 'RERUNS_DELAY',   defaultValue: '1',                 description: '失败重试间隔（秒）')
        choice(name: 'PARALLEL', choices: ['off', 'auto', '2', '3','4','5', '10'], description: '并发模式: off=串行, auto=自动检测CPU核心数, 数字=指定worker数')
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
        DINGTALK_WEBHOOK   = 'https://oapi.dingtalk.com/robot/send?access_token=c55a542c2e9782b0cf1c9863aae885c44f1ae4732fdd65066b1ebefe909844f6'
        DINGTALK_KEYWORD   = '测试'
    }

    stages {
        stage('0. 获取构建用户') {
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

        stage('1. 拉取代码') {
            options { retry(3) }
            steps {
                echo "正在从 Git 拉取代码..."
                script {
                    def gitConfig = [branch: env.GIT_BRANCH, url: env.GIT_URL]
                    if (env.GIT_CREDENTIALS_ID?.trim()) {
                        gitConfig.credentialsId = env.GIT_CREDENTIALS_ID
                    }
                    git gitConfig
                }
            }
        }

        stage('2. 安装依赖') {
            steps {
                echo "正在安装 Python 依赖..."
                bat """
                    chcp 65001
                    "${PYTHON_PATH}" -m pip install -r requirements.txt -q -i ${PIP_INDEX_URL} --cache-dir .pip-cache
                """
            }
        }

        stage('2.5 确保 Mock 服务') {
            when { expression { params.ENV == 'dev' } }
            steps {
                echo "探测 Mock 服务，未运行则自动启动..."
                bat """
                    chcp 65001
                    "${PYTHON_PATH}" scripts/ensure_mock.py --env ${params.ENV}
                """
            }
        }

        stage('3. 执行测试') {
            steps {
                echo "开始执行 Pytest 测试..."
                script {
                    catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                        // 拼接 mark 参数
                        def markArg = params.MARK != 'all' ? "-m ${params.MARK}" : ""

                        // 根据用户选择拼接 xdist 参数
                        def xdistArg = ''
                        switch (params.PARALLEL) {
                            case 'off':
                                xdistArg = ''
                                echo "📌 串行模式"
                                break
                            case 'auto':
                                xdistArg = '-n auto'
                                echo "📌 并发模式: auto (自动检测CPU核心数)"
                                break
                            default:
                                xdistArg = "-n ${params.PARALLEL}"
                                echo "📌 并发模式: ${params.PARALLEL} workers"
                                break
                        }

                        bat """
                            chcp 65001
                            "${PYTHON_PATH}" -m pytest ${markArg} ${xdistArg} ^
                                --env=${params.ENV} ^
                                --alluredir=${ALLURE_RESULTS} ^
                                --clean-alluredir ^
                                --reruns ${params.RERUNS} ^
                                --reruns-delay ${params.RERUNS_DELAY} ^
                                -v
                        """
                    }
                }
            }
        }

        stage('3.5 写入 Allure 环境 & 执行器信息') {
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

        stage('4. 生成 Allure 报告') {
            steps {
                allure includeProperties: false,
                       jdk: '',
                       results: [[path: 'reports/allure-results']],
                       reportBuildPolicy: 'ALWAYS'
            }
        }
    }

    post {
        always {
            echo "流水线执行结束"
            archiveArtifacts artifacts: 'logs/*.log', allowEmptyArchive: true
        }
        success {
            echo "✅ 恭喜！所有测试用例通过！"
            script { notifyAll('SUCCESS', 'green', '✅') }
        }
        failure {
            echo "❌ 存在失败的测试用例，请查看 Allure 报告。"
            script { notifyAll('FAILURE', 'red', '❌') }
        }
    }
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
        echo "⚠️ 钉钉通知失败: ${e.message}"
    }
}

// ================================================================
//  根据环境参数返回 base_url（读取 config/config.yaml）
// ================================================================
def getBaseUrl(String envName) {
    def output = bat(
        script: """
            @echo off
            chcp 65001 >nul
            "${env.PYTHON_PATH}" -c "from common.yaml_handler import get_config; print(get_config('${envName}')['base_url'])"
        """,
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