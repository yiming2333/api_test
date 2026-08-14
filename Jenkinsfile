pipeline {
    agent any

    parameters {
        choice(name: 'ENV', choices: ['dev', 'prod'], description: '选择运行环境')
        choice(name: 'MARK', choices: ['all', 'smoke', 'regression'], description: '选择用例标记')
    }

    environment {
        PYTHON_PATH = 'C:/Users/27088/AppData/Local/Programs/Python/Python310/python.exe'
        ALLURE_RESULTS = 'reports/allure-results'
        ALLURE_REPORT   = 'reports/allure-report'
        PYTHONIOENCODING = 'utf-8'   // 解决 Windows 控制台编码问题
    }

    stages {
        stage('1. 拉取代码') {
            options { retry(3) }
            steps {
                echo "正在从 Git 拉取代码..."
                git branch: 'master', url: 'https://github.com/yiming2333/api_test.git'
            }
        }

        stage('2. 安装依赖') {
            steps {
                echo "正在安装 Python 依赖..."
                bat """
                    chcp 65001
                    ${PYTHON_PATH} -m pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple
                """
            }
        }

        stage('3. 执行测试') {
            steps {
                echo "开始执行 Pytest 测试..."
                script {
                    catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                        def markArg = params.MARK != 'all' ? "-m ${params.MARK}" : ""
                        bat """
                            ${PYTHON_PATH} -m pytest ${markArg} ^
                                --env=${params.ENV} ^
                                --alluredir=${ALLURE_RESULTS} ^
                                --clean-alluredir ^
                                -v
                        """
                    }
                }
            }
        }

        stage('4. 生成并发布 Allure 报告') {
            steps {
                echo "正在生成 Allure 测试报告..."
                // 使用命令行生成报告（确保 allure 命令在 PATH 中）
                bat """
                    allure generate ${ALLURE_RESULTS} -o ${ALLURE_REPORT} --clean
                """
                // 通过 HTML Publisher 发布报告
                publishHTML([
                    reportDir: 'reports/allure-report',
                    reportFiles: 'index.html',
                    reportName: 'Allure 测试报告',
                    allowMissing: true,
                    keepAll: false,
                    alwaysLinkToLastBuild: false
                ])
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
            // 发送成功邮件（包含 Allure 报告链接）
            emailext (
                subject: "✅ 测试通过 - ${env.JOB_NAME} - Build #${env.BUILD_NUMBER}",
                body: """
                    <p>各位同事，大家好！</p>
                    <p>项目 <strong>${env.JOB_NAME}</strong> 构建成功！</p>
                    <ul>
                        <li>构建编号：<strong>#${env.BUILD_NUMBER}</strong></li>
                        <li>构建状态：<span style="color: green;">✅ SUCCESS</span></li>
                        <li>触发人：${env.BUILD_USER_ID ?: '未知'}</li>
                        <li>测试报告：<a href="${env.BUILD_URL}allure/">${env.BUILD_URL}allure/</a></li>
                    </ul>
                    <p>请点击上方链接查看 Allure 测试报告详情。</p>
                    <hr/>
                    <p style="font-size: 12px; color: gray;">此邮件由 Jenkins 自动发送，请勿回复。</p>
                """,
                mimeType: 'text/html'
                // 如果不指定 to，将使用系统配置中的默认收件人
                // 如需指定多个收件人，可添加 to: 'user1@example.com, user2@example.com'
            )
        }

        failure {
            echo "❌ 存在失败的测试用例，请查看 Allure 报告。"
            // 发送失败邮件（包含 Allure 报告链接）
            emailext (
                subject: "❌ 测试失败 - ${env.JOB_NAME} - Build #${env.BUILD_NUMBER}",
                body: """
                    <p>各位同事，大家好！</p>
                    <p>项目 <strong>${env.JOB_NAME}</strong> 构建失败，请及时处理！</p>
                    <ul>
                        <li>构建编号：<strong>#${env.BUILD_NUMBER}</strong></li>
                        <li>构建状态：<span style="color: red;">❌ FAILURE</span></li>
                        <li>触发人：${env.BUILD_USER_ID ?: '未知'}</li>
                        <li>测试报告：<a href="${env.BUILD_URL}allure/">${env.BUILD_URL}allure/</a></li>
                    </ul>
                    <p>请点击上方链接查看 Allure 测试报告详情，并排查失败原因。</p>
                    <hr/>
                    <p style="font-size: 12px; color: gray;">此邮件由 Jenkins 自动发送，请勿回复。</p>
                """,
                mimeType: 'text/html'
            )
        }
    }
}